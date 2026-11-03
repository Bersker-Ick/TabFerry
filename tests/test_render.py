from __future__ import annotations

import unittest

from tabferry.models import Snapshot, Tab
from tabferry.render import render


def sample_snapshot() -> Snapshot:
    return Snapshot(
        tabs=[
            Tab(url="https://alpha.example/", title="Alpha", source="test"),
            Tab(url="https://beta.example/path?a=1&b=2", title="", source="test"),
        ],
        created_at="2025-01-02T03:04:05+00:00",
        source="test",
    )


class RenderTests(unittest.TestCase):
    def test_render_contains_data_and_no_tokens(self):
        html = render(sample_snapshot(), ["https://alpha.example/"])
        self.assertIn("TabFerry", html)
        self.assertIn("https://beta.example/path?a=1&b=2", html)
        self.assertIn("var PRELOADED =", html)
        for token in ("__TABFERRY_DATA__", "__TABFERRY_PRELOADED__", "__TABFERRY_TOTAL__",
                      "__TABFERRY_DUPES__", "__TABFERRY_REVISION__", "__TABFERRY_ID__",
                      "__TABFERRY_GENERATED__", "__TABFERRY_SOURCE__"):
            self.assertNotIn(token, html)

    def test_preloaded_state_is_embedded(self):
        html = render(sample_snapshot(), ["https://alpha.example/"])
        self.assertIn('"https://alpha.example/"', html)
        self.assertIn("PRELOADED", html)

    def test_script_payload_cannot_close_tag(self):
        snapshot = Snapshot(
            tabs=[Tab(url="https://example.com/</script>", title="</script>")],
            created_at="2025-01-02T03:04:05+00:00",
            source="test",
        )
        html = render(snapshot)
        self.assertNotIn("</script></script>", html)

    def test_bilingual_ui_strings_are_present(self):
        html = render(sample_snapshot())
        self.assertIn("Removed", html)
        self.assertIn("已移除", html)
        self.assertIn("离线副本", html)


if __name__ == "__main__":
    unittest.main()
