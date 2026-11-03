from __future__ import annotations

import os
import struct
import tempfile
import time
import unittest
from pathlib import Path

from tabferry.sources import chromium

CMD_UPDATE_TAB_NAVIGATION = 6
CMD_SET_SELECTED_NAVIGATION_INDEX = 7


def _pad4(raw: bytes) -> bytes:
    return raw + b"\0" * ((-len(raw)) % 4)


def _str(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack("<I", len(raw)) + _pad4(raw)


def _str16(value: str) -> bytes:
    raw = value.encode("utf-16-le")
    return struct.pack("<I", len(value)) + _pad4(raw)


def _pickle(body: bytes) -> bytes:
    return struct.pack("<I", len(body)) + body


def _command(command_id: int, payload: bytes) -> bytes:
    return struct.pack("<H", len(payload) + 1) + bytes([command_id]) + payload


def _navigation(tab_id: int, index: int, url: str, title: str = "") -> bytes:
    body = struct.pack("<ii", tab_id, index) + _str(url) + _str16(title)
    return _command(CMD_UPDATE_TAB_NAVIGATION, _pickle(body))


def _selected(tab_id: int, index: int) -> bytes:
    payload = struct.pack("<ii", tab_id, index)
    return _command(CMD_SET_SELECTED_NAVIGATION_INDEX, payload)


def _session(*commands: bytes) -> bytes:
    return b"SNSS" + struct.pack("<i", 3) + b"".join(commands)


class ChromiumParserTests(unittest.TestCase):
    def test_selected_navigation_wins(self):
        data = _session(
            _navigation(101, 0, "https://alpha.example/", "Alpha"),
            _navigation(101, 1, "https://alpha.example/two", "Alpha two"),
            _selected(101, 0),
            _navigation(202, 0, "https://beta.example/", "Beta"),
            _navigation(202, 1, "https://beta.example/two", "Beta two"),
        )
        tabs = chromium.tabs_from_bytes(data)
        self.assertEqual([tab.url for tab in tabs], [
            "https://alpha.example/",
            "https://beta.example/two",
        ])

    def test_unicode_title_and_alignment(self):
        data = _session(
            _navigation(7, 0, "https://example.com/a?b=1", "标签页 · 测试"),
            _selected(7, 0),
        )
        tabs = chromium.tabs_from_bytes(data)
        self.assertEqual(tabs[0].title, "标签页 · 测试")

    def test_internal_urls_are_filtered(self):
        data = _session(
            _navigation(1, 0, "chrome://settings/"),
            _navigation(2, 0, "edge://flags/"),
            _navigation(3, 0, "https://keep.example/", "Keep"),
        )
        tabs = chromium.tabs_from_bytes(data)
        self.assertEqual([tab.url for tab in tabs], ["https://keep.example/"])

    def test_selecting_a_missing_entry_falls_back_to_last(self):
        data = _session(
            _navigation(9, 0, "https://first.example/"),
            _navigation(9, 1, "https://second.example/"),
            _selected(9, 99),
        )
        tabs = chromium.tabs_from_bytes(data)
        self.assertEqual(tabs[0].url, "https://second.example/")

    def test_bad_magic(self):
        with self.assertRaises(chromium.SnssError):
            chromium.tabs_from_bytes(b"NOPE" + b"\0" * 8)

    def test_pickle_style_pair_is_accepted(self):
        payload = _pickle(struct.pack("<ii", 42, 1))
        data = _session(
            _navigation(42, 0, "https://zero.example/"),
            _navigation(42, 1, "https://one.example/"),
            _command(CMD_SET_SELECTED_NAVIGATION_INDEX, payload),
        )
        tabs = chromium.tabs_from_bytes(data)
        self.assertEqual(tabs[0].url, "https://one.example/")


class ChromiumDiscoveryTests(unittest.TestCase):
    def test_find_profiles_and_session_preference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            default = root / "Default" / "Sessions"
            default.mkdir(parents=True)
            (default / "Session_1").write_bytes(_session())
            (default / "Tabs_9").write_bytes(_session())
            profile1 = root / "Profile 1" / "Sessions"
            profile1.mkdir(parents=True)
            (profile1 / "Session_2").write_bytes(_session())

            names = [path.name for path in chromium.find_profiles(root)]
            self.assertEqual(names, ["Default", "Profile 1"])

            # Session_* beats a newer Tabs_* file: Tabs is the closed-tab list.
            now = time.time()
            os.utime(default / "Session_1", (now, now))
            os.utime(default / "Tabs_9", (now + 30, now + 30))
            self.assertEqual(chromium.session_file(root / "Default"), default / "Session_1")

    def test_load_from_profile_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "Default"
            sessions = profile / "Sessions"
            sessions.mkdir(parents=True)
            data = _session(
                _navigation(5, 0, "https://loaded.example/", "Loaded"),
                _selected(5, 0),
            )
            (sessions / "Session_123").write_bytes(data)

            tabs = chromium.load(profile=str(profile))
            self.assertEqual([tab.url for tab in tabs], ["https://loaded.example/"])

            # A "User Data" root should find the profile underneath it.
            tabs_root = chromium.load(profile=tmp)
            self.assertEqual([tab.url for tab in tabs_root], ["https://loaded.example/"])

    def test_unknown_browser(self):
        with self.assertRaises(Exception):
            chromium.load("netscape")


if __name__ == "__main__":
    unittest.main()
