"""HTTP server: serves the app plus a tiny state API."""

from __future__ import annotations

import json
import logging
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import List, Optional
from urllib.parse import urlparse

from . import __version__
from .config import Paths
from .render import render
from .snapshot import load as load_snapshot
from .state import StateStore

log = logging.getLogger(__name__)

MAX_BODY = 256 * 1024


class App:
    """Everything a running TabFerry instance needs."""

    def __init__(self, paths: Paths):
        self.paths = paths.ensure()
        self.snapshot = load_snapshot(paths.tabs_path)
        self.state = StateStore(paths.state_path)
        self.html = render(self.snapshot, self.state.removed())

    def server(self, host: str, port: int) -> ThreadingHTTPServer:
        httpd = ThreadingHTTPServer((host, port), make_handler(self))
        httpd.daemon_threads = True
        return httpd


def _read_json(handler: BaseHTTPRequestHandler):
    try:
        length = int(handler.headers.get("Content-Length") or 0)
    except ValueError:
        return None
    if length <= 0 or length > MAX_BODY:
        return None
    try:
        raw = handler.rfile.read(length)
        return json.loads(raw.decode("utf-8"))
    except (OSError, ValueError):
        return None


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TabFerry/" + __version__

        def log_message(self, fmt, *args):  # noqa: A003
            log.info("%s %s", self.address_string(), fmt % args)

        def _send(
            self,
            code: int,
            body,
            content_type: str = "text/plain; charset=utf-8",
            extra: Optional[dict] = None,
        ) -> None:
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        def _json(self, code: int, payload) -> None:
            self._send(code, json.dumps(payload, ensure_ascii=False),
                       "application/json; charset=utf-8")

        def do_OPTIONS(self):  # noqa: N802
            self._send(204, b"", "text/plain", {
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            })

        def do_GET(self):  # noqa: N802
            path = urlparse(self.path).path
            if path in ("/", "/index.html", "/app.html"):
                self._send(200, app.html, "text/html; charset=utf-8")
                return
            if path == "/download":
                body = render(app.snapshot, app.state.removed())
                self._send(200, body, "text/html; charset=utf-8", {
                    "Content-Disposition": 'attachment; filename="tabferry.html"',
                })
                return
            if path == "/api/state":
                self._json(200, app.state.to_dict())
                return
            if path == "/health":
                self._json(200, {
                    "ok": True,
                    "version": __version__,
                    "tabs": len(app.snapshot.tabs),
                    "removed": app.state.count(),
                })
                return
            if path == "/favicon.ico":
                self._send(204, b"", "image/x-icon")
                return
            self._json(404, {"error": "not found"})

        def do_HEAD(self):  # noqa: N802
            self.do_GET()

        def do_POST(self):  # noqa: N802
            path = urlparse(self.path).path
            if path not in ("/api/remove", "/api/restore", "/api/restore_all"):
                self._json(404, {"error": "not found"})
                return
            payload = _read_json(self)
            if payload is None:
                self._json(400, {"error": "expected a JSON object"})
                return
            url = str(payload.get("url") or "").strip() if isinstance(payload, dict) else ""

            changed = False
            if path == "/api/remove":
                changed = app.state.remove(url)
            elif path == "/api/restore":
                changed = app.state.restore(url)
            else:
                changed = app.state.restore_all() > 0

            self._json(200, {
                "ok": True,
                "changed": changed,
                "removed": app.state.count(),
            })

    return Handler


def local_ip() -> Optional[str]:
    """Best-effort LAN address, without sending any traffic."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def urls_for(host: str, port: int) -> List[str]:
    """Human-usable URLs for a server bound to ``host``."""
    if host in ("0.0.0.0", "::", ""):
        urls = [f"http://127.0.0.1:{port}/"]
        ip = local_ip()
        if ip and ip != "127.0.0.1":
            urls.append(f"http://{ip}:{port}/")
        return urls
    return [f"http://{host}:{port}/"]
