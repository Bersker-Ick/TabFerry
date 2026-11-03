"""Render the single-file web app from a snapshot."""

from __future__ import annotations

import html
import json
from importlib.resources import files
from typing import Iterable, Optional

from .models import Snapshot
from .util import domain_of, stable_id

DATA_TOKEN = "/*__TABFERRY_DATA__*/[]"
PRELOADED_TOKEN = "/*__TABFERRY_PRELOADED__*/[]"


def _script_json(value) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    # A literal </script> inside the payload would close the tag early.
    return text.replace("</", "<\\/")


def template_text() -> str:
    resource = files("tabferry") / "templates" / "app.html"
    return resource.read_text(encoding="utf-8")


def render(
    snapshot: Snapshot,
    removed: Optional[Iterable[str]] = None,
    title: str = "TabFerry",
    revision: int = 0,
) -> str:
    """Return the complete HTML app for ``snapshot``.

    ``removed`` is baked into the page as ``PRELOADED`` so a downloaded offline
    copy starts with the same state as the server.
    """
    data = [
        {
            "u": tab.url,
            "t": tab.display_title(),
            "d": domain_of(tab.url),
        }
        for tab in snapshot.tabs
    ]
    payload = _script_json(data)
    preloaded = _script_json(list(removed or []))
    data_id = stable_id("\n".join(tab.url for tab in snapshot.tabs))

    out = template_text()
    replacements = {
        DATA_TOKEN: payload,
        PRELOADED_TOKEN: preloaded,
        "__TABFERRY_TOTAL__": str(len(data)),
        "__TABFERRY_DUPES__": str(snapshot.duplicates_merged),
        "__TABFERRY_REVISION__": str(revision),
        "__TABFERRY_ID__": data_id,
        "__TABFERRY_GENERATED__": html.escape(snapshot.created_at or "unknown"),
        "__TABFERRY_SOURCE__": html.escape(snapshot.source or "unknown"),
        "__TABFERRY_TITLE__": html.escape(title),
    }
    for key, value in replacements.items():
        out = out.replace(key, value)
    return out
