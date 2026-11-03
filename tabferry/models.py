"""Tab and snapshot data model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class Tab:
    """One open page, browser-agnostic."""

    url: str
    title: str = ""
    window: int = 1
    pinned: bool = False
    source: str = ""

    def display_title(self) -> str:
        return self.title.strip() or self.url

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "window": self.window,
            "pinned": self.pinned,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Tab":
        if isinstance(data, str):
            return cls(url=data.strip())
        if not isinstance(data, dict):
            raise TypeError("tab must be an object or a URL string")
        url = str(data.get("url") or "").strip()
        if not url:
            raise ValueError("tab is missing a url")
        try:
            window = int(data.get("window") or 1)
        except (TypeError, ValueError):
            window = 1
        return cls(
            url=url,
            title=str(data.get("title") or "").strip(),
            window=max(1, window),
            pinned=bool(data.get("pinned")),
            source=str(data.get("source") or "").strip(),
        )


@dataclass
class Snapshot:
    """A point-in-time list of tabs plus provenance."""

    tabs: List[Tab]
    created_at: str
    source: str
    version: int = 1
    dedupe: str = "url"
    duplicates_merged: int = 0
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at or self.created_at,
            "source": self.source,
            "dedupe": self.dedupe,
            "duplicates_merged": self.duplicates_merged,
            "tabs": [tab.to_dict() for tab in self.tabs],
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Snapshot":
        if not isinstance(data, dict):
            raise ValueError("snapshot must be a JSON object")
        raw_tabs = data.get("tabs")
        if not isinstance(raw_tabs, list):
            raise ValueError("snapshot is missing a tabs array")
        tabs: List[Tab] = []
        for item in raw_tabs:
            tab = Tab.from_dict(item)
            if tab.url:
                tabs.append(tab)
        try:
            duplicates = int(data.get("duplicates_merged") or 0)
        except (TypeError, ValueError):
            duplicates = 0
        return cls(
            tabs=tabs,
            created_at=str(data.get("created_at") or ""),
            source=str(data.get("source") or "unknown"),
            version=int(data.get("version") or 1),
            dedupe=str(data.get("dedupe") or "url"),
            duplicates_merged=max(0, duplicates),
            updated_at=str(data.get("updated_at") or data.get("created_at") or ""),
        )
