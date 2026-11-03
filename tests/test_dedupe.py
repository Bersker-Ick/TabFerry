from __future__ import annotations

import unittest

from tabferry.models import Snapshot, Tab
from tabferry.util import dedupe_key, dedupe_tabs, normalize_url


class NormalizeUrlTests(unittest.TestCase):
    def test_fragment_tracking_www_and_port(self):
        noisy = "https://www.Example.com:443/Path/?utm_source=x&b=2&a=1#section"
        clean = "https://example.com/Path?a=1&b=2"
        self.assertEqual(normalize_url(noisy), normalize_url(clean))

    def test_trailing_slash_is_ignored(self):
        self.assertEqual(
            normalize_url("https://example.com/docs/"),
            normalize_url("https://example.com/docs"),
        )

    def test_query_order_is_ignored(self):
        self.assertEqual(
            normalize_url("https://example.com/?b=2&a=1"),
            normalize_url("https://example.com/?a=1&b=2"),
        )

    def test_non_http_only_loses_fragment(self):
        self.assertEqual(normalize_url("mailto:me@example.com#x"), "mailto:me@example.com")

    def test_different_paths_stay_different(self):
        self.assertNotEqual(
            normalize_url("https://example.com/a"),
            normalize_url("https://example.com/b"),
        )

    def test_dedupe_key_modes(self):
        url = "https://example.com/?utm_source=x#top"
        self.assertEqual(dedupe_key(url, "none"), url)
        self.assertEqual(dedupe_key(url, "url"), "https://example.com/?utm_source=x")
        self.assertEqual(dedupe_key(url, "normalized"), "https://example.com/")


class DedupeTabsTests(unittest.TestCase):
    def test_modes(self):
        tabs = [
            Tab(url="https://example.com/?utm_source=x", title="one"),
            Tab(url="https://example.com/", title="two"),
            Tab(url="https://example.com/#anchor", title="three"),
        ]
        self.assertEqual(len(dedupe_tabs(tabs, mode="none")), 3)
        self.assertEqual(len(dedupe_tabs(tabs, mode="url")), 2)
        self.assertEqual(len(dedupe_tabs(tabs, mode="normalized")), 1)
        self.assertEqual(dedupe_tabs(tabs, mode="normalized")[0].title, "one")

    def test_none_keeps_exact_duplicates(self):
        tabs = [Tab(url="https://example.com/"), Tab(url="https://example.com/")]
        self.assertEqual(len(dedupe_tabs(tabs, mode="none")), 2)

    def test_order_is_preserved(self):
        tabs = [Tab(url="https://b.example/"), Tab(url="https://a.example/")]
        self.assertEqual([tab.url for tab in dedupe_tabs(tabs, mode="normalized")],
                         ["https://b.example/", "https://a.example/"])


class SnapshotMetadataTests(unittest.TestCase):
    def test_dedupe_fields_roundtrip(self):
        snapshot = Snapshot(
            tabs=[Tab(url="https://example.com/")],
            created_at="2025-01-02T03:04:05+00:00",
            source="test",
            dedupe="normalized",
            duplicates_merged=7,
        )
        restored = Snapshot.from_dict(snapshot.to_dict())
        self.assertEqual(restored.dedupe, "normalized")
        self.assertEqual(restored.duplicates_merged, 7)

    def test_old_snapshots_default_to_url(self):
        restored = Snapshot.from_dict({
            "created_at": "2025-01-02T03:04:05+00:00",
            "source": "test",
            "tabs": [{"url": "https://example.com/"}],
        })
        self.assertEqual(restored.dedupe, "url")
        self.assertEqual(restored.duplicates_merged, 0)


if __name__ == "__main__":
    unittest.main()
