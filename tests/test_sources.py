from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tabferry.sources.json_source import load as load_json
from tabferry.sources.text import load as load_text
from tabferry.sources.text import parse_line


class TextSourceTests(unittest.TestCase):
    def test_parse_variants(self):
        self.assertEqual(parse_line("https://example.com/").url, "https://example.com/")
        self.assertEqual(
            parse_line("Example\thttps://example.com/").title, "Example"
        )
        self.assertEqual(
            parse_line("https://example.com/\tExample").title, "Example"
        )
        self.assertIsNone(parse_line("# comment"))
        self.assertIsNone(parse_line("not a url"))

    def test_load_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "urls.txt"
            path.write_text(
                "# exported tabs\n"
                "https://one.example/\n"
                "Two\thttps://two.example/\n"
                "\n",
                encoding="utf-8",
            )
            tabs = load_text(str(path))
            self.assertEqual([tab.url for tab in tabs], ["https://one.example/", "https://two.example/"])
            self.assertEqual(tabs[1].title, "Two")

    def test_missing_file(self):
        with self.assertRaises(Exception):
            load_text("/definitely/missing/urls.txt")


class JsonSourceTests(unittest.TestCase):
    def test_snapshot_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tabs.json"
            path.write_text(
                json.dumps({"tabs": [{"url": "https://a.example/", "title": "A"}]}),
                encoding="utf-8",
            )
            tabs = load_json(str(path))
            self.assertEqual(len(tabs), 1)
            self.assertEqual(tabs[0].title, "A")

    def test_array_of_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tabs.json"
            path.write_text(json.dumps(["https://a.example/", "https://b.example/"]), encoding="utf-8")
            tabs = load_json(str(path))
            self.assertEqual(len(tabs), 2)

    def test_bad_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tabs.json"
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(Exception):
                load_json(str(path))


if __name__ == "__main__":
    unittest.main()
