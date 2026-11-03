"""Source adapters: turn a browser's local data into :class:`~tabferry.models.Tab`."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ..models import Tab


class SourceError(RuntimeError):
    """Raised when a source cannot locate or read its input."""


class TabSource(ABC):
    """A place tabs can be imported from."""

    name: str = ""
    description: str = ""

    @abstractmethod
    def load(self) -> List[Tab]:
        """Return the tabs this source currently exposes."""


__all__ = ["SourceError", "TabSource"]
