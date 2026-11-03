"""Plain-text URL list importer.

Accepted lines::

    https://example.com/
    Example title<TAB>https://example.com/
    https://example.com/<TAB>Example title
    # comments and blank lines are ignored
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..models import Tab
from .base import SourceError, TabSource

_URL_PREFIXES = ("http://", "https://", "ftp://", "file://")


def _looks_like_url(value: str) -> bool:
    return value.strip().lower().startswith(_URL_PREFIXES)


def parse_line(line: str, line_number: int = 0) -> Optional[Tab]:
    text = line.strip()
    if not text or text.startswith("#"):
        return None

    if "\t" in text:
        left, right = (part.strip() for part in text.split("\t", 1))
        if _looks_like_url(left):
            return Tab(url=left, title=right)
        if _looks_like_url(right):
            return Tab(url=right, title=left)
        return None

    if _looks_like_url(text):
        return Tab(url=text)
    return None


def load(path: str) -> List[Tab]:
    target = Path(path).expanduser()
    if not target.is_file():
        raise SourceError(f"URL list not found: {target}")
    tabs: List[Tab] = []
    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise SourceError(f"cannot read {target}: {exc}") from exc
    for number, line in enumerate(lines, 1):
        tab = parse_line(line, number)
        if tab is not None:
            tabs.append(tab)
    if not tabs:
        raise SourceError(f"no URLs found in {target}")
    return tabs


class TextSource(TabSource):
    name = "text"
    description = "One URL per line (optionally title<TAB>url)"

    def __init__(self, path: str):
        self.path = path

    def load(self) -> List[Tab]:
        return load(self.path)
