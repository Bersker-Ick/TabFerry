"""Source registry used by the CLI."""

from __future__ import annotations

from typing import Dict, Type

from .base import SourceError, TabSource
from .chromium import BROWSERS, ChromiumSource, load as load_chromium
from .firefox import FirefoxSource, find_profiles, load as load_firefox
from .json_source import JsonSource
from .text import TextSource

SOURCES: Dict[str, Type[TabSource]] = {
    "firefox": FirefoxSource,
    "chromium": ChromiumSource,
    "text": TextSource,
    "json": JsonSource,
}


def get_source(name: str) -> Type[TabSource]:
    try:
        return SOURCES[name]
    except KeyError:
        raise SourceError(f"unknown source {name!r}; available: {', '.join(sorted(SOURCES))}")


def names() -> list:
    return sorted(SOURCES)


__all__ = [
    "BROWSERS",
    "SOURCES",
    "SourceError",
    "TabSource",
    "ChromiumSource",
    "FirefoxSource",
    "JsonSource",
    "TextSource",
    "find_profiles",
    "get_source",
    "load_chromium",
    "load_firefox",
    "names",
]
