from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tabferry.config import resolve_paths
from tabferry.models import Snapshot, Tab
from tabferry.server import App
from tabferry.snapshot import load as load_snapshot
from tabferry.snapshot import save


def make_app(tmp: str) -> App:
    data = Path(tmp)
    snapshot = Snapshot(
        tabs=[Tab(url="https://existing.example/", title="Existing")],
        created_at="2025-01-02T03:04:05+00:00",
        updated_at="2025-01-02T03:04:05+00:00",
        source="test",
    )
    save(snapshot, data / "tabs.json")
    return App(resolve_paths(str(data)))


class WatchAddTests(unittest.TestCase):
    def test_add_tabs_dedupes_and_skips_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = make_app(tmp)
            app.state.remove("https://removed.example/")

            added = app.add_tabs([
                Tab(url="https://existing.example/", title="duplicate"),
                Tab(url="https://existing.example/?utm_source=x", title="tracking"),
                Tab(url="https://new.example/", title="New"),
                Tab(url="https://removed.example/", title="Removed"),
                Tab(url="https://new.example/#frag", title="New anchor"),
            ])

            self.assertEqual([tab.url for tab in added], ["https://new.example/"])
            self.assertEqual(app.info()["tabs"], 2)
            self.assertEqual(app.info()["revision"], 1)

            updates, revision = app.updates_since(0)
            self.assertEqual(revision, 1)
            self.assertEqual(updates, [
                {"u": "https://new.example/", "t": "New", "d": "new.example"},
            ])

            reloaded = load_snapshot(app.paths.tabs_path)
            self.assertEqual(len(reloaded.tabs), 2)
            self.assertEqual(reloaded.updated_at, app.snapshot.updated_at)

    def test_no_new_tabs_does_not_bump_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = make_app(tmp)
            self.assertEqual(app.add_tabs([Tab(url="https://existing.example/")]), [])
            self.assertEqual(app.info()["revision"], 0)
            self.assertEqual(app.updates_since(0), ([], 0))

    def test_mode_none_keeps_url_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = make_app(tmp)
            added = app.add_tabs(
                [Tab(url="https://existing.example/?utm_source=x", title="variant")],
                mode="none",
            )
            self.assertEqual(len(added), 1)
            self.assertEqual(app.info()["tabs"], 2)

    def test_updates_since_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = make_app(tmp)
            app.add_tabs([Tab(url="https://one.example/", title="One")])
            app.add_tabs([Tab(url="https://two.example/", title="Two")])

            first, revision = app.updates_since(0)
            self.assertEqual(revision, 2)
            self.assertEqual([item["u"] for item in first],
                             ["https://one.example/", "https://two.example/"])

            second, _ = app.updates_since(1)
            self.assertEqual([item["u"] for item in second], ["https://two.example/"])

            none, _ = app.updates_since(2)
            self.assertEqual(none, [])


if __name__ == "__main__":
    unittest.main()
