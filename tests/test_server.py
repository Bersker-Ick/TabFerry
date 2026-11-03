from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tabferry.config import resolve_paths
from tabferry.models import Snapshot, Tab
from tabferry.server import App
from tabferry.snapshot import save


def write_snapshot(data_dir: Path) -> None:
    snapshot = Snapshot(
        tabs=[
            Tab(url="https://alpha.example/", title="Alpha", source="test"),
            Tab(url="https://beta.example/", title="Beta", source="test"),
        ],
        created_at="2025-01-02T03:04:05+00:00",
        source="test",
    )
    save(snapshot, data_dir / "tabs.json")


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name)
        write_snapshot(self.data_dir)
        self.app = App(resolve_paths(str(self.data_dir)))
        self.httpd = self.app.server("127.0.0.1", 0)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def get(self, path: str):
        return urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5)

    def post(self, path: str, payload: dict):
        request = Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return urlopen(request, timeout=5)

    def test_health(self):
        with self.get("/health") as response:
            body = json.loads(response.read())
        self.assertTrue(body["ok"])
        self.assertEqual(body["tabs"], 2)
        self.assertEqual(body["removed"], 0)

    def test_index_and_state(self):
        with self.get("/") as response:
            html = response.read().decode("utf-8")
        self.assertIn("TabFerry", html)
        with self.get("/api/state") as response:
            state = json.loads(response.read())
        self.assertEqual(state["removed"], [])

    def test_remove_and_restore(self):
        with self.post("/api/remove", {"url": "https://alpha.example/"}) as response:
            body = json.loads(response.read())
        self.assertTrue(body["changed"])
        self.assertEqual(body["removed"], 1)
        with self.get("/api/state") as response:
            state = json.loads(response.read())
        self.assertEqual(state["removed"], ["https://alpha.example/"])

        with self.post("/api/restore", {"url": "https://alpha.example/"}) as response:
            body = json.loads(response.read())
        self.assertTrue(body["changed"])
        self.assertEqual(body["removed"], 0)

    def test_download_is_attachment_with_state(self):
        self.post("/api/remove", {"url": "https://beta.example/"}).read()
        with self.get("/download") as response:
            disposition = response.headers.get("Content-Disposition", "")
            html = response.read().decode("utf-8")
        self.assertIn("attachment", disposition)
        self.assertIn("https://beta.example/", html)

    def test_bad_payload(self):
        with self.post("/api/remove", {"nope": True}) as response:
            body = json.loads(response.read())
        self.assertEqual(response.status, 200)
        self.assertFalse(body["changed"])
        # Missing/invalid JSON body should be a 400.
        request = Request(
            f"http://127.0.0.1:{self.port}/api/remove",
            data=b"not json",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as ctx2:
            urlopen(request, timeout=5)
        self.assertEqual(ctx2.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
