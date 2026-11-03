"""Small shared helpers: time, URLs, hashing and atomic writes."""

from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, TypeVar
from urllib.parse import urlsplit

T = TypeVar("T")

#: Pages a browser owns rather than the user: never worth ferrying.
INTERNAL_PREFIXES = (
    "about:blank",
    "about:newtab",
    "about:home",
    "about:welcome",
    "about:privatebrowsing",
    "about:sessionrestore",
    "about:restartrequired",
    "chrome://",
    "resource://",
    "moz-extension://",
    "edge://",
    "devtools://",
)


def now_iso() -> str:
    """Current local time as an ISO-8601 string with offset."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def is_internal_url(url: str) -> bool:
    """True for blank pages and browser-internal URLs."""
    return not url or url.startswith(INTERNAL_PREFIXES)


def dedupe_key(url: str) -> str:
    """Key used to merge the same page opened at different anchors."""
    return url.split("#", 1)[0].strip()


def domain_of(url: str) -> str:
    """Best-effort hostname for display, without a leading ``www.``."""
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def stable_id(text: str, length: int = 10) -> str:
    """Short, stable hash used as the offline storage namespace."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def dedupe_tabs(tabs: Iterable[T], key=None) -> List[T]:
    """Drop later tabs that resolve to the same URL key, keeping order."""
    seen = set()
    out: List[T] = []
    get_key = key or (lambda tab: dedupe_key(tab.url))
    for tab in tabs:
        k = get_key(tab)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(tab)
    return out


def atomic_write_text(path: os.PathLike, text: str, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` via a temp file + atomic replace."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def truncate(text: str, limit: int = 120) -> str:
    """Shorten a string for logs and terminal output."""
    return text if len(text) <= limit else text[: limit - 1] + "…"
