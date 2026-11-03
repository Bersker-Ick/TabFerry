from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tabferry.sources import firefox
from tests.helpers import SESSION, write_session


class FirefoxSourceTests(unittest.TestCase):
    def test_tabs_from_session_skips_internal(self):
        tabs = list(firefox.tabs_from_session(SESSION))
        urls = [tab.url for tab in tabs]
        self.assertIn("https://alpha.example/", urls)
        self.assertIn("https://beta.example/two", urls)
        self.assertIn("https://alpha.example/#section", urls)
        self.assertNotIn("about:newtab", urls)
        self.assertNotIn("about:blank", urls)
        self.assertEqual(len(tabs), 3)
        self.assertEqual(tabs[1].window, 1)
        self.assertEqual(tabs[1].source, "firefox")

    def test_load_from_explicit_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "abc.default"
            write_session(profile, SESSION)
            tabs = firefox.load(str(profile))
            self.assertEqual(len(tabs), 3)
            self.assertEqual(tabs[0].title, "Alpha")

    def test_missing_profile(self):
        with self.assertRaises(firefox.SourceError):
            firefox.load("/definitely/not/a/profile")

    def test_find_profiles_reads_ini(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Profiles" / "abc.default").mkdir(parents=True)
            (root / "profiles.ini").write_text(
                "[Profile0]\n"
                "Name=default\n"
                "IsRelative=1\n"
                "Path=Profiles/abc.default\n"
                "Default=1\n",
                encoding="utf-8",
            )
            profiles = firefox.find_profiles(root)
            self.assertEqual(len(profiles), 1)
            self.assertTrue(profiles[0].is_default)
            self.assertEqual(profiles[0].path, (root / "Profiles" / "abc.default").resolve())

    def test_session_file_prefers_newest(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            write_session(profile, SESSION)
            backups = profile / "sessionstore-backups"
            backups.mkdir()
            recovery = backups / "recovery.jsonlz4"
            recovery.write_bytes((profile / "sessionstore.jsonlz4").read_bytes())
            # Make the backup strictly newer than the base file.
            import os
            import time

            newer = time.time() + 20
            os.utime(recovery, (newer, newer))
            self.assertEqual(firefox.session_file(profile), recovery)


if __name__ == "__main__":
    unittest.main()
