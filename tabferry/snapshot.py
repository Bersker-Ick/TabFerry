"""Persisted snapshot: the imported tab list."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from .models import Snapshot
from .util import atomic_write_text


class SnapshotError(ValueError):
    """Raised when a snapshot file is missing or malformed."""


def save(snapshot: Snapshot, path: Union[str, Path]) -> None:
    atomic_write_text(path, json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2))


def load(path: Union[str, Path], allow_empty: bool = False) -> Snapshot:
    target = Path(path)
    if not target.exists():
        raise SnapshotError(f"no snapshot at {target}")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        snapshot = Snapshot.from_dict(data)
    except (OSError, ValueError, TypeError) as exc:
        raise SnapshotError(f"cannot read snapshot {target}: {exc}") from exc
    if not snapshot.tabs and not allow_empty:
        raise SnapshotError(f"snapshot {target} contains no tabs")
    return snapshot


def exists(path: Union[str, Path]) -> bool:
    return Path(path).exists()
