"""Source registry used by the CLI."""

from __future__ import annotations

from typing import Dict, Type

from .base import SourceError, TabSource
from .firefox import FirefoxSource, find_profiles, load as load_firefox
from .json_source import JsonSource
from .text import TextSource

SOURCES: Dict[str, Type[TabSource]] = {
    "firefox": FirefoxSource,
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
    "SOURCES",
    "SourceError",
    "TabSource",
    "FirefoxSource",
    "JsonSource",
    "TextSource",
    "find_profiles",
    "get_source",
    "load_firefox",
    "names",
]
