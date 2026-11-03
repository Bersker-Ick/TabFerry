"""Chromium-family session importer (Chrome, Edge, Brave, Chromium).

Open tabs live in ``<profile>/Sessions/Session_<timestamp>`` as an SNSS
journal: a header followed by length-prefixed commands. The command we need is
``kCommandUpdateTabNavigation`` (6), whose payload is a Chromium Pickle:

    int32 tab_id
    int32 navigation_index
    string url            (uint32 length, bytes, padded to 4)
    string16 title        (uint32 character count, UTF-16LE, padded to 4)
    ... navigation state we do not need

``kCommandSetSelectedNavigationIndex`` (7) tells us which entry is current.
"""

from __future__ import annotations

import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from ..models import Tab
from ..util import is_internal_url
from .base import SourceError, TabSource

SNSS_MAGIC = b"SNSS"
CMD_UPDATE_TAB_NAVIGATION = 6
CMD_SET_SELECTED_NAVIGATION_INDEX = 7

BROWSERS = {
    "chrome": {
        "windows": r"Google\Chrome\User Data",
        "macos": "Google/Chrome",
        "linux": ".config/google-chrome",
    },
    "edge": {
        "windows": r"Microsoft\Edge\User Data",
        "macos": "Microsoft Edge",
        "linux": ".config/microsoft-edge",
    },
    "brave": {
        "windows": r"BraveSoftware\Brave-Browser\User Data",
        "macos": "BraveSoftware/Brave-Browser",
        "linux": ".config/BraveSoftware/Brave-Browser",
    },
    "chromium": {
        "windows": r"Chromium\User Data",
        "macos": "Chromium",
        "linux": ".config/chromium",
    },
}


class SnssError(ValueError):
    """Raised for malformed SNSS data."""


@dataclass(frozen=True)
class SessionFile:
    path: Path
    browser: str
    profile: Path
    mtime: float


def _platform() -> str:
    if os.name == "nt":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def browser_root(browser: str) -> Optional[Path]:
    """Default ``User Data`` directory for a browser, if it exists."""
    rel = BROWSERS.get(browser, {}).get(_platform())
    if not rel:
        return None
    if _platform() == "windows":
        base = Path(os.environ.get("LOCALAPPDATA", ""))
    elif _platform() == "macos":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home()
    root = base / rel
    return root if root.is_dir() else None


def find_profiles(root: Path) -> List[Path]:
    """Profile directories under a ``User Data`` root."""
    root = Path(root).expanduser()
    if not root.is_dir():
        return []
    profiles = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if (child / "Sessions").is_dir() or child.name == "Default" or child.name.startswith("Profile"):
            if child.name in ("Sessions", "Snapshots"):
                continue
            profiles.append(child)
    return profiles


def session_file(profile: Path) -> Optional[Path]:
    """Newest live session file in a profile.

    ``Session_*`` is the open-tab journal; ``Tabs_*`` is the recently-closed
    list, so it is only used as a fallback for very old layouts.
    """
    profile = Path(profile).expanduser()
    sessions = profile / "Sessions"
    primary: List[Path] = []
    fallback: List[Path] = []
    if sessions.is_dir():
        primary.extend(sessions.glob("Session_*"))
        fallback.extend(sessions.glob("Tabs_*"))
    primary.append(profile / "Current Session")
    fallback.append(profile / "Current Tabs")

    candidates = [path for path in primary if path.is_file()]
    if not candidates:
        candidates = [path for path in fallback if path.is_file()]
    if not candidates:
        return None
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0]


def _u32(data: bytes, offset: int) -> int:
    if offset + 4 > len(data):
        raise SnssError("truncated uint32")
    return struct.unpack_from("<I", data, offset)[0]


def _i32(data: bytes, offset: int) -> int:
    if offset + 4 > len(data):
        raise SnssError("truncated int32")
    return struct.unpack_from("<i", data, offset)[0]


def _align4(value: int) -> int:
    return (value + 3) & ~3


def _string(data: bytes, offset: int) -> Tuple[str, int]:
    length = _u32(data, offset)
    start = offset + 4
    end = start + length
    if end > len(data):
        raise SnssError("truncated string")
    value = data[start:end].decode("utf-8", "replace")
    return value, start + _align4(length)


def _string16(data: bytes, offset: int) -> Tuple[str, int]:
    chars = _u32(data, offset)
    start = offset + 4
    end = start + chars * 2
    if end > len(data):
        raise SnssError("truncated UTF-16 string")
    value = data[start:end].decode("utf-16-le", "replace")
    return value, start + _align4(chars * 2)


def iter_commands(data: bytes) -> Iterable[Tuple[int, bytes]]:
    """Yield ``(command_id, payload)`` from an SNSS file."""
    if len(data) < 8 or data[:4] != SNSS_MAGIC:
        raise SnssError("not an SNSS session file")
    version = _i32(data, 4)
    if version < 1 or version > 4:
        raise SnssError(f"unsupported SNSS version {version}")

    offset = 8
    while offset + 3 <= len(data):
        size = struct.unpack_from("<H", data, offset)[0]
        if size < 1:
            break
        end = offset + 2 + size
        if end > len(data):
            raise SnssError("truncated SNSS command")
        command_id = data[offset + 2]
        payload = data[offset + 3 : end]
        yield command_id, payload
        offset = end


def parse_update_tab_navigation(payload: bytes) -> Tuple[int, int, str, str]:
    """Decode one ``kCommandUpdateTabNavigation`` payload."""
    if len(payload) < 4:
        raise SnssError("short navigation payload")
    _ = _u32(payload, 0)  # Pickle payload length; fields start after it
    tab_id = _i32(payload, 4)
    index = _i32(payload, 8)
    url, offset = _string(payload, 12)
    title, _ = _string16(payload, offset)
    return tab_id, index, url, title


def parse_pair(payload: bytes) -> Tuple[int, int]:
    """Decode a two-int command payload (e.g. selected navigation index).

    Navigation commands are Pickles with a 4-byte length header, but the
    selection/index commands are raw ``int32`` pairs (8 bytes) in files written
    by current Chromium. Accept both shapes.
    """
    if len(payload) == 8:
        return _i32(payload, 0), _i32(payload, 4)
    if len(payload) >= 12:
        if _u32(payload, 0) == len(payload) - 4:
            return _i32(payload, 4), _i32(payload, 8)
        return _i32(payload, 0), _i32(payload, 4)
    raise SnssError("short pair payload")


def tabs_from_bytes(data: bytes) -> List[Tab]:
    """Extract one tab per session tab, at its selected navigation entry."""
    navigations: Dict[int, Dict[int, Tuple[str, str]]] = {}
    selected: Dict[int, int] = {}

    for command_id, payload in iter_commands(data):
        try:
            if command_id == CMD_UPDATE_TAB_NAVIGATION:
                tab_id, index, url, title = parse_update_tab_navigation(payload)
                if url:
                    navigations.setdefault(tab_id, {})[index] = (url, title)
            elif command_id == CMD_SET_SELECTED_NAVIGATION_INDEX:
                tab_id, index = parse_pair(payload)
                selected[tab_id] = index
        except SnssError:
            continue

    tabs: List[Tab] = []
    for tab_id, entries in navigations.items():
        if not entries:
            continue
        index = selected.get(tab_id)
        if index is None or index not in entries:
            index = max(entries)
        url, title = entries[index]
        if not url or is_internal_url(url):
            continue
        tabs.append(Tab(url=url, title=title.strip(), window=1, source="chromium"))
    return tabs


def load(browser: str = "auto", profile: Optional[str] = None) -> List[Tab]:
    """Import open tabs from a Chromium-family browser.

    ``profile`` may be a profile directory, a ``User Data`` root, or a session
    file. With ``browser="auto"`` the profile with the newest session wins.
    """
    if profile:
        path = Path(profile).expanduser()
        if path.is_file():
            return _read_session(path)
        if not path.is_dir():
            raise SourceError(f"Chromium profile not found: {path}")
        if (path / "Sessions").is_dir() or path.name == "Default":
            target = session_file(path)
            if target:
                return _read_session(target)
        candidates = []
        for item in find_profiles(path):
            target = session_file(item)
            if target:
                candidates.append((target.stat().st_mtime, item, target))
        if not candidates:
            raise SourceError(f"no session files under {path}")
        candidates.sort(key=lambda item: item[0], reverse=True)
        return _read_session(candidates[0][2])

    browsers = [browser] if browser != "auto" else list(BROWSERS)
    if browser not in BROWSERS and browser != "auto":
        raise SourceError(f"unknown browser {browser!r}; choose from {', '.join(BROWSERS)}")

    found: List[SessionFile] = []
    for name in browsers:
        root = browser_root(name)
        if root is None:
            continue
        for item in find_profiles(root):
            target = session_file(item)
            if target:
                found.append(SessionFile(target, name, item, target.stat().st_mtime))
    if not found:
        raise SourceError(
            "No Chromium session found. Pass --profile PATH, or install/launch "
            "Chrome, Edge, Brave or Chromium once."
        )
    found.sort(key=lambda item: item.mtime, reverse=True)

    errors = []
    for item in found:
        try:
            return _read_session(item.path)
        except (OSError, SnssError, SourceError) as exc:
            errors.append(f"{item.path}: {exc}")
    raise SourceError(
        "Could not read a Chromium session (is the browser running?). "
        "Close the browser or copy the profile, then retry. "
        + "; ".join(errors)
    )


def _read_session(path: Path) -> List[Tab]:
    try:
        data = Path(path).read_bytes()
    except PermissionError as exc:
        raise SourceError(
            f"permission denied reading {path}; close the browser or copy the profile"
        ) from exc
    tabs = tabs_from_bytes(data)
    if not tabs:
        raise SourceError(f"no open tabs found in {path}")
    return tabs


class ChromiumSource(TabSource):
    name = "chromium"
    description = "Chrome / Edge / Brave / Chromium session files (SNSS)"

    def __init__(self, browser: str = "auto", profile: Optional[str] = None):
        self.browser = browser
        self.profile = profile

    def load(self) -> List[Tab]:
        return load(self.browser, self.profile)
