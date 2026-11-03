"""Background watcher: poll a browser session and append newly opened tabs."""

from __future__ import annotations

import logging
import threading
from typing import Callable, List

from .models import Tab
from .server import App
from .sources.base import SourceError

log = logging.getLogger(__name__)


class Watcher(threading.Thread):
    """A daemon thread that periodically feeds new tabs into an :class:`App`.

    ``loader`` is a zero-argument callable returning a list of
    :class:`~tabferry.models.Tab`. Duplicate URLs are dropped by
    ``App.add_tabs`` using the configured dedupe mode, and tabs the user
    explicitly removed are never resurrected.
    """

    def __init__(
        self,
        app: App,
        loader: Callable[[], List[Tab]],
        interval: float = 5.0,
        mode: str = "normalized",
    ):
        super().__init__(name="tabferry-watcher", daemon=True)
        self.app = app
        self.loader = loader
        self.interval = max(1.0, float(interval))
        self.mode = mode
        self._stop = threading.Event()
        self._last_error = None

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        log.info("watching every %.1fs (dedupe=%s)", self.interval, self.mode)
        while not self._stop.is_set():
            try:
                tabs = self.loader()
                added = self.app.add_tabs(tabs, mode=self.mode)
                if added:
                    log.info(
                        "detected %d new tab(s); total %d",
                        len(added),
                        self.app.info()["tabs"],
                    )
                if self._last_error is not None:
                    log.info("source is readable again")
                    self._last_error = None
            except SourceError as exc:
                message = str(exc)
                if message != self._last_error:
                    log.warning("source unavailable: %s", message)
                    self._last_error = message
            except Exception:  # noqa: BLE001
                log.exception("watch iteration failed")
            self._stop.wait(self.interval)
