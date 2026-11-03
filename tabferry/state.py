"""Thread-safe, atomically persisted set of removed tabs."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .util import atomic_write_text, now_iso

log = logging.getLogger(__name__)


class StateStore:
    """Tracks which URLs the user has triaged away.

    The on-disk shape is ``{"version": 1, "updated": ..., "removed": {url: iso}}``.
    A plain list is also accepted when loading for forward/backward tolerance.
    """

    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._removed: Dict[str, str] = {}
        self._updated: Optional[str] = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("ignoring unreadable state file %s: %s", self.path, exc)
            return
        if not isinstance(data, dict):
            return
        self._updated = data.get("updated") if isinstance(data.get("updated"), str) else None
        raw = data.get("removed")
        if isinstance(raw, dict):
            self._removed = {str(k): str(v) for k, v in raw.items() if str(k).strip()}
        elif isinstance(raw, list):
            stamp = self._updated or ""
            self._removed = {str(url): stamp for url in raw if str(url).strip()}

    def _save(self) -> None:
        self._updated = now_iso()
        payload = {"version": 1, "updated": self._updated, "removed": dict(self._removed)}
        atomic_write_text(self.path, json.dumps(payload, ensure_ascii=False, indent=2))

    # -- reads ---------------------------------------------------------

    def removed(self) -> List[str]:
        with self._lock:
            return list(self._removed)

    def is_removed(self, url: str) -> bool:
        with self._lock:
            return url in self._removed

    def count(self) -> int:
        with self._lock:
            return len(self._removed)

    def updated(self) -> Optional[str]:
        with self._lock:
            return self._updated

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "version": 1,
                "updated": self._updated,
                "removed": list(self._removed),
            }

    # -- writes --------------------------------------------------------

    def remove(self, url: str) -> bool:
        url = (url or "").strip()
        if not url:
            return False
        with self._lock:
            if url in self._removed:
                return False
            self._removed[url] = now_iso()
            self._save()
            return True

    def restore(self, url: str) -> bool:
        url = (url or "").strip()
        with self._lock:
            if url not in self._removed:
                return False
            del self._removed[url]
            self._save()
            return True

    def restore_all(self) -> int:
        with self._lock:
            count = len(self._removed)
            if count:
                self._removed.clear()
                self._save()
            return count
