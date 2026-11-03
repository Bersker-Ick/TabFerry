from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tabferry.state import StateStore


class StateStoreTests(unittest.TestCase):
    def test_add_remove_and_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = StateStore(path)
            self.assertEqual(store.count(), 0)
            self.assertTrue(store.remove("https://a.example/"))
            self.assertFalse(store.remove("https://a.example/"))
            self.assertTrue(store.is_removed("https://a.example/"))
            self.assertEqual(store.removed(), ["https://a.example/"])
            self.assertTrue(path.exists())

            reloaded = StateStore(path)
            self.assertEqual(reloaded.removed(), ["https://a.example/"])
            self.assertTrue(reloaded.restore("https://a.example/"))
            self.assertFalse(reloaded.restore("https://a.example/"))
            self.assertEqual(reloaded.count(), 0)

    def test_restore_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(Path(tmp) / "state.json")
            store.remove("https://a.example/")
            store.remove("https://b.example/")
            self.assertEqual(store.restore_all(), 2)
            self.assertEqual(store.count(), 0)
            self.assertEqual(store.restore_all(), 0)

    def test_accepts_legacy_list_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(json.dumps({"removed": ["https://a.example/"]}), encoding="utf-8")
            store = StateStore(path)
            self.assertEqual(store.removed(), ["https://a.example/"])

    def test_ignores_corrupt_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{not json", encoding="utf-8")
            store = StateStore(path)
            self.assertEqual(store.count(), 0)

    def test_blank_url_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(Path(tmp) / "state.json")
            self.assertFalse(store.remove("   "))


if __name__ == "__main__":
    unittest.main()
