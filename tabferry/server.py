"""HTTP server: serves the app, the state API and live tab updates."""

from __future__ import annotations

import json
import logging
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from . import __version__
from .config import Paths
from .models import Snapshot, Tab
from .render import render
from .snapshot import load as load_snapshot, save as save_snapshot
from .state import StateStore
from .util import dedupe_key, domain_of, now_iso

log = logging.getLogger(__name__)

MAX_BODY = 256 * 1024


class App:
    """Everything a running TabFerry instance needs.

    The snapshot can grow at runtime (the watcher appends newly opened tabs),
    so all reads and writes go through ``_lock`` and the rendered page is
    regenerated whenever the revision changes.
    """

    def __init__(self, paths: Paths, allow_empty: bool = False):
        self.paths = paths.ensure()
        self.snapshot = load_snapshot(paths.tabs_path, allow_empty=allow_empty)
        self.state = StateStore(paths.state_path)
        self._lock = threading.RLock()
        self._revision = 0
        # (revision, [{u,t,d}, ...]) for tabs discovered by the watcher.
        self._history: List[Tuple[int, List[Dict[str, str]]]] = []
        self._html = ""
        with self._lock:
            self._render_locked()

    # -- rendering -----------------------------------------------------

    def _render_locked(self) -> None:
        self._html = render(self.snapshot, self.state.removed(), revision=self._revision)

    def html_bytes(self) -> bytes:
        with self._lock:
            return self._html.encode("utf-8")

    def download_html(self) -> str:
        with self._lock:
            return render(self.snapshot, self.state.removed(), revision=self._revision)

    # -- reads ---------------------------------------------------------

    def info(self) -> Dict[str, object]:
        with self._lock:
            return {
                "ok": True,
                "revision": self._revision,
                "tabs": len(self.snapshot.tabs),
                "removed": self.state.count(),
                "updated_at": self.snapshot.updated_at or self.snapshot.created_at,
            }

    def updates_since(self, since: int) -> Tuple[List[Dict[str, str]], int]:
        with self._lock:
            tabs: List[Dict[str, str]] = []
            for revision, payload in self._history:
                if revision > since:
                    tabs.extend(payload)
            return tabs, self._revision

    # -- live additions ------------------------------------------------

    def add_tabs(self, tabs: List[Tab], mode: str = "normalized") -> List[Tab]:
        """Append tabs that are new after dedupe and not explicitly removed."""
        with self._lock:
            existing = {dedupe_key(tab.url, mode) for tab in self.snapshot.tabs}
            existing.discard("")
            added: List[Tab] = []
            for tab in tabs:
                key = dedupe_key(tab.url, mode)
                if not key or key in existing:
                    continue
                if self.state.is_removed(tab.url):
                    continue
                existing.add(key)
                self.snapshot.tabs.append(tab)
                added.append(tab)

            if not added:
                return []

            self.snapshot.updated_at = now_iso()
            save_snapshot(self.snapshot, self.paths.tabs_path)
            self._revision += 1
            payload = [
                {"u": tab.url, "t": tab.display_title(), "d": domain_of(tab.url)}
                for tab in added
            ]
            self._history.append((self._revision, payload))
            if len(self._history) > 200:
                self._history = self._history[-200:]
            self._render_locked()
            return added

    # -- server --------------------------------------------------------

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
            parsed = urlparse(self.path)
            path = parsed.path
            if path in ("/", "/index.html", "/app.html"):
                self._send(200, app.html_bytes(), "text/html; charset=utf-8")
                return
            if path == "/download":
                self._send(200, app.download_html(), "text/html; charset=utf-8", {
                    "Content-Disposition": 'attachment; filename="tabferry.html"',
                })
                return
            if path == "/api/state":
                self._json(200, app.state.to_dict())
                return
            if path == "/api/version":
                self._json(200, app.info())
                return
            if path == "/api/updates":
                query = parse_qs(parsed.query)
                try:
                    since = int(query.get("since", ["0"])[0])
                except (TypeError, ValueError):
                    since = 0
                tabs, revision = app.updates_since(max(0, since))
                self._json(200, {"revision": revision, "tabs": tabs})
                return
            if path == "/health":
                info = app.info()
                info["version"] = __version__
                self._json(200, info)
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
