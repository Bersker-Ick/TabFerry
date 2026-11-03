"""Firefox session-store importer.

Firefox keeps the current session in ``sessionstore.jsonlz4`` (written on a
clean shutdown) and a live copy in ``sessionstore-backups/recovery.jsonlz4``.
Profiles are discovered through ``profiles.ini`` on Windows, macOS, Linux,
Flatpak and Snap installs.
"""

from __future__ import annotations

import configparser
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional

from .. import mozlz4
from ..models import Tab
from ..util import is_internal_url
from .base import SourceError, TabSource


@dataclass(frozen=True)
class FirefoxProfile:
    name: str
    path: Path
    is_default: bool = False


def candidate_roots() -> List[Path]:
    """Well-known Firefox data directories for the current platform."""
    roots: List[Path] = []
    override = os.environ.get("TABFERRY_FIREFOX_ROOT")
    if override:
        roots.append(Path(override).expanduser())

    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            roots.append(Path(appdata) / "Mozilla" / "Firefox")
    elif sys.platform == "darwin":
        roots.append(Path.home() / "Library" / "Application Support" / "Firefox")
    else:
        roots.append(Path.home() / ".mozilla" / "firefox")
        roots.append(Path.home() / ".var" / "app" / "org.mozilla.firefox" / ".mozilla" / "firefox")
        roots.append(Path.home() / "snap" / "firefox" / "common" / ".mozilla" / "firefox")

    seen = set()
    out: List[Path] = []
    for root in roots:
        root = root.expanduser()
        if root.is_dir() and root not in seen:
            seen.add(root)
            out.append(root)
    return out


def _profiles_in_root(root: Path) -> List[FirefoxProfile]:
    root = root.expanduser()
    profiles: List[FirefoxProfile] = []
    ini = root / "profiles.ini"
    default_rel: Optional[str] = None

    if ini.exists():
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            parser.read(ini, encoding="utf-8")
        except (OSError, configparser.Error):
            parser = configparser.ConfigParser(interpolation=None, strict=False)

        for section in parser.sections():
            if section.startswith("Install") and parser.has_option(section, "Default"):
                default_rel = parser.get(section, "Default")

        for section in parser.sections():
            if not section.startswith("Profile"):
                continue
            raw = parser.get(section, "Path", fallback="") or ""
            if not raw:
                continue
            is_relative = parser.getboolean(section, "IsRelative", fallback=True)
            path = (root / raw) if is_relative else Path(raw)
            path = path.expanduser()
            try:
                path = path.resolve()
            except OSError:
                pass
            if default_rel:
                try:
                    default_path = (root / default_rel).expanduser().resolve()
                except OSError:
                    default_path = root / default_rel
            else:
                default_path = None
            is_default = parser.getboolean(section, "Default", fallback=False) or (
                default_path is not None and path == default_path
            )
            if path.is_dir():
                profiles.append(
                    FirefoxProfile(parser.get(section, "Name", fallback=path.name), path, is_default)
                )

    if not profiles:
        for path in sorted(root.glob("*.default*")):
            if path.is_dir():
                profiles.append(FirefoxProfile(path.name, path.resolve(), "default" in path.name))

    unique = {}
    for profile in profiles:
        unique.setdefault(profile.path, profile)
    return list(unique.values())


def find_profiles(root: Optional[Path] = None) -> List[FirefoxProfile]:
    """Find Firefox profiles under one root, or all known roots."""
    roots = [Path(root)] if root else candidate_roots()
    profiles: List[FirefoxProfile] = []
    for item in roots:
        profiles.extend(_profiles_in_root(item))
    unique = {}
    for profile in profiles:
        unique.setdefault(profile.path, profile)
    return list(unique.values())


def session_file(profile_path: Path) -> Optional[Path]:
    """Newest session file in a profile, or ``None``."""
    candidates = [
        profile_path / "sessionstore.jsonlz4",
        profile_path / "sessionstore-backups" / "recovery.jsonlz4",
        profile_path / "sessionstore-backups" / "previous.jsonlz4",
    ]
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        return None
    existing.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return existing[0]


def _entry_for_tab(tab: Any) -> Any:
    if not isinstance(tab, dict):
        return {}
    entries = tab.get("entries") or []
    if not entries:
        return {}
    raw_index = tab.get("index", len(entries))
    try:
        index = int(raw_index)
    except (TypeError, ValueError):
        index = len(entries)
    index = max(1, min(index, len(entries)))
    entry = entries[index - 1]
    return entry if isinstance(entry, dict) else {}


def tabs_from_session(session: Any) -> Iterable[Tab]:
    """Yield public tabs from a parsed Firefox session document."""
    if not isinstance(session, dict):
        return
    windows = session.get("windows") or []
    if not isinstance(windows, list):
        return
    for window_index, window in enumerate(windows, 1):
        if not isinstance(window, dict):
            continue
        raw_tabs = window.get("tabs") or []
        if not isinstance(raw_tabs, list):
            continue
        for tab in raw_tabs:
            tab_data = tab if isinstance(tab, dict) else {}
            entry = _entry_for_tab(tab_data)
            url = str(entry.get("url") or "").strip()
            if not url:
                url = str(tab_data.get("userTypedValue") or "").strip()
            if not url or is_internal_url(url):
                continue
            yield Tab(
                url=url,
                title=str(entry.get("title") or "").strip(),
                window=window_index,
                pinned=bool(tab_data.get("pinned")),
                source="firefox",
            )


def load(profile: Optional[str] = None) -> List[Tab]:
    """Import tabs from a Firefox profile (path override or auto-discovery)."""
    if profile:
        path = Path(profile).expanduser()
        if not path.is_dir():
            raise SourceError(f"Firefox profile directory not found: {path}")
        profiles = [FirefoxProfile(path.name, path, True)]
    else:
        profiles = find_profiles()
        if not profiles:
            raise SourceError(
                "No Firefox profile found. Pass --profile PATH or set TABFERRY_FIREFOX_ROOT."
            )
        profiles.sort(key=lambda item: (not item.is_default, item.name))

    errors: List[str] = []
    for item in profiles:
        path = session_file(item.path)
        if path is None:
            continue
        try:
            session = mozlz4.load(path)
        except (OSError, ValueError) as exc:
            errors.append(f"{path}: {exc}")
            continue
        tabs = list(tabs_from_session(session))
        if tabs:
            return tabs

    detail = ("; ".join(errors)) if errors else "no session file with open tabs"
    raise SourceError(f"Could not import tabs from Firefox ({detail}).")


class FirefoxSource(TabSource):
    name = "firefox"
    description = "Firefox session store (sessionstore.jsonlz4)"

    def __init__(self, profile: Optional[str] = None):
        self.profile = profile

    def load(self) -> List[Tab]:
        return load(self.profile)
