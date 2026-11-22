"""Tiny localhost HTTP listener that lets a browser button hand URLs to the web clipper.

Endpoints (127.0.0.1 only):
    GET  /ping                 -> {"app": "toolbelt-web-clipper"}
    GET  /clip?url=<url>       -> hands the URL to the app (add &format=json for a JSON reply)
    POST /clip  {"url": "..."} -> same, JSON body or form-encoded
    GET  /focus                -> brings the app window to the front

Requests carrying a web page ``Origin`` are rejected, and the ``Host`` header must be
localhost, so ordinary websites can't drive it through fetch() or DNS rebinding.
The app only previews URLs it receives; nothing is saved without the user.
"""

import html
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional
from urllib.parse import parse_qs, quote, urlsplit

APP_ID = "toolbelt-web-clipper"
DEFAULT_PORT = int(os.environ.get("WEB_CLIPPER_PORT", "47811"))
_EXTENSION_SCHEMES = ("chrome-extension://", "moz-extension://", "safari-web-extension://")
_MAX_BODY = 64 * 1024


def origin_allowed(origin: Optional[str]) -> bool:
    """Browser extensions and plain navigations (no Origin header) are allowed; web pages are not."""
    if not origin:
        return True
    return origin.startswith(_EXTENSION_SCHEMES)


def host_allowed(host: Optional[str], port: int) -> bool:
    return (host or "") in (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}")


def is_web_url(url: str) -> bool:
    parts = urlsplit(url or "")
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def bookmarklet(port: int = DEFAULT_PORT) -> str:
    return (
        "javascript:(()=>{window.open('http://127.0.0.1:%d/clip?url='+encodeURIComponent(location.href),"
        "'webclipper','width=380,height=170')})()" % port
    )


_SENT_PAGE = """<!doctype html><meta charset="utf-8"><title>Web Clipper</title>
<body style="font:15px -apple-system,system-ui,sans-serif;margin:24px;color:#1f2328">
<b>&#10003; Sent to Web Clipper</b><p style="color:#57606a;word-break:break-all">{url}</p>
<script>setTimeout(function(){{window.close()}},900)</script></body>"""


class _Handler(BaseHTTPRequestHandler):
    server: "ClipServer._Server"

    def log_message(self, *args):
        pass

    def _reply(self, status: int, body: str, content_type: str = "application/json"):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, payload: dict):
        self._reply(status, json.dumps(payload))

    def _guard(self) -> bool:
        if not host_allowed(self.headers.get("Host"), self.server.server_address[1]):
            self._json(403, {"error": "bad host"})
            return False
        if not origin_allowed(self.headers.get("Origin")):
            self._json(403, {"error": "origin not allowed"})
            return False
        return True

    def do_GET(self):
        if not self._guard():
            return
        parts = urlsplit(self.path)
        query = parse_qs(parts.query)
        if parts.path == "/ping":
            self._json(200, {"app": APP_ID, "ok": True})
        elif parts.path == "/focus":
            self.server.on_focus()
            self._json(200, {"ok": True})
        elif parts.path == "/clip":
            self._clip((query.get("url") or [""])[0], (query.get("format") or [""])[0] == "json")
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._guard():
            return
        if urlsplit(self.path).path != "/clip":
            self._json(404, {"error": "not found"})
            return
        length = min(int(self.headers.get("Content-Length") or 0), _MAX_BODY)
        raw = self.rfile.read(length).decode("utf-8", "replace")
        if "json" in (self.headers.get("Content-Type") or ""):
            try:
                url = str(json.loads(raw).get("url", ""))
            except (ValueError, AttributeError):
                url = ""
        else:
            url = (parse_qs(raw).get("url") or [""])[0]
        self._clip(url, as_json=True)

    def _clip(self, url: str, as_json: bool):
        url = url.strip()
        if not is_web_url(url):
            self._json(400, {"error": "expected an http(s) url"})
            return
        self.server.on_url(url)
        if as_json:
            self._json(200, {"ok": True, "url": url})
        else:
            self._reply(200, _SENT_PAGE.format(url=html.escape(url)), "text/html")


class ClipServer:
    """Runs the listener on a daemon thread. Callbacks run on that thread."""

    class _Server(ThreadingHTTPServer):
        daemon_threads = True
        on_url: Callable[[str], None]
        on_focus: Callable[[], None]

    def __init__(self, on_url: Callable[[str], None], on_focus: Optional[Callable[[], None]] = None,
                 port: int = DEFAULT_PORT, host: str = "127.0.0.1"):
        self.on_url = on_url
        self.on_focus = on_focus or (lambda: None)
        self.port = port
        self.host = host
        self._server: Optional[ClipServer._Server] = None

    def start(self) -> int:
        """Bind and start serving; returns the port. Raises OSError if the port is taken."""
        server = self._Server((self.host, self.port), _Handler)
        server.on_url = self.on_url
        server.on_focus = self.on_focus
        self._server = server
        self.port = server.server_address[1]
        threading.Thread(target=server.serve_forever, name="clip-bridge", daemon=True).start()
        return self.port

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


# System/env proxies (macOS network settings, http_proxy) must not see loopback requests.
_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _get(port: int, path: str, timeout: float) -> Optional[dict]:
    try:
        with _LOCAL_OPENER.open(f"http://127.0.0.1:{port}{path}", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return None


def is_running(port: int = DEFAULT_PORT, timeout: float = 1.0) -> bool:
    """True if a web clipper (not some other program) is listening on ``port``."""
    reply = _get(port, "/ping", timeout)
    return bool(reply and reply.get("app") == APP_ID)


def send_url(url: str, port: int = DEFAULT_PORT, timeout: float = 2.0) -> bool:
    """Hand ``url`` to an already-running clipper. Returns False if none is listening."""
    if not is_running(port, timeout):
        return False
    reply = _get(port, "/clip?format=json&url=" + quote(url, safe=""), timeout)
    return bool(reply and reply.get("ok"))


def focus_running(port: int = DEFAULT_PORT, timeout: float = 1.0) -> bool:
    return is_running(port, timeout) and bool(_get(port, "/focus", timeout))
