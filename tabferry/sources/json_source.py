"""JSON importer for TabFerry snapshots and simple URL arrays."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

from ..models import Tab
from .base import SourceError, TabSource


def _items(data: Any) -> List[Any]:
    if isinstance(data, dict) and isinstance(data.get("tabs"), list):
        return data["tabs"]
    if isinstance(data, list):
        return data
    raise SourceError("JSON must be a snapshot object or an array of tabs/URLs")


def load(path: str) -> List[Tab]:
    target = Path(path).expanduser()
    if not target.is_file():
        raise SourceError(f"JSON file not found: {target}")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SourceError(f"cannot read {target}: {exc}") from exc

    tabs: List[Tab] = []
    for item in _items(data):
        try:
            tab = Tab.from_dict(item)
        except (TypeError, ValueError):
            continue
        if tab.url:
            tabs.append(tab)
    if not tabs:
        raise SourceError(f"no usable tabs in {target}")
    return tabs


class JsonSource(TabSource):
    name = "json"
    description = "TabFerry snapshot or an array of {url, title} objects"

    def __init__(self, path: str):
        self.path = path

    def load(self) -> List[Tab]:
        return load(self.path)
