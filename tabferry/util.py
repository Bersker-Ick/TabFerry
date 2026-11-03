"""Small shared helpers: time, URLs, hashing and atomic writes."""

from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
    "chrome-extension://",
    "chrome-untrusted://",
    "brave://",
    "opera://",
    "vivaldi://",
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


#: Query parameters that identify a campaign/click, not a page.
TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "yclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "mkt_tok",
    "_ga",
    "_gl",
    "ref",
    "ref_src",
    "ref_url",
    "spm",
    "scm",
    "share_source",
    "share_medium",
    "share_plat",
    "share_tag",
    "share_session_id",
    "from_source",
    "from_spmid",
    "vd_source",
}


def normalize_url(url: str) -> str:
    """Canonical key for duplicate detection.

    Lowercases the scheme/host, drops ``www.``, default ports, fragments,
    tracking parameters and a trailing slash, and sorts the remaining query
    parameters. URLs that are not HTTP(S) only lose their fragment.
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw.split("#", 1)[0]
    if parts.scheme.lower() not in ("http", "https"):
        return raw.split("#", 1)[0]

    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    try:
        port = parts.port
    except ValueError:
        port = None
    if port and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"

    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_KEYS:
            continue
        pairs.append((key, value))
    pairs.sort()
    query = urlencode(pairs, doseq=True)

    return urlunsplit((scheme, host, path, query, ""))


def dedupe_key(url: str, mode: str = "url") -> str:
    """Key used to merge the same page opened more than once."""
    if mode == "none":
        return (url or "").strip()
    if mode == "normalized":
        return normalize_url(url)
    return (url or "").split("#", 1)[0].strip()


def stable_id(text: str, length: int = 10) -> str:
    """Short, stable hash used as the offline storage namespace."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def dedupe_tabs(tabs: Iterable[T], key=None, mode: str = "url") -> List[T]:
    """Drop later tabs that resolve to the same key, keeping order."""
    if key is None and mode == "none":
        return list(tabs)
    seen = set()
    out: List[T] = []
    get_key = key or (lambda tab: dedupe_key(tab.url, mode))
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
