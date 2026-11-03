"""Application paths and platform defaults."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

APP_NAME = "TabFerry"
APP_SLUG = "tabferry"


def default_data_dir() -> Path:
    """Per-user data directory, overridable with ``TABFERRY_DATA_DIR``."""
    override = os.environ.get("TABFERRY_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / APP_SLUG


@dataclass(frozen=True)
class Paths:
    """Files that make up one TabFerry installation."""

    data_dir: Path

    @property
    def tabs_path(self) -> Path:
        return self.data_dir / "tabs.json"

    @property
    def state_path(self) -> Path:
        return self.data_dir / "state.json"

    def ensure(self) -> "Paths":
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self


def resolve_paths(data_dir: Optional[str] = None) -> Paths:
    """Turn an optional ``--data-dir`` value into a :class:`Paths`."""
    if data_dir:
        return Paths(Path(data_dir).expanduser())
    return Paths(default_data_dir())
