"""Test helpers, including a tiny literal-only LZ4 encoder."""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

MAGIC = b"mozLz40\0"


def lz4_literal_block(payload: bytes) -> bytes:
    """Encode ``payload`` as one all-literals LZ4 sequence (valid, no matches)."""
    out = bytearray()
    size = len(payload)
    if size < 15:
        out.append(size << 4)
    else:
        out.append(0xF0)
        rest = size - 15
        while rest >= 255:
            out.append(255)
            rest -= 255
        out.append(rest)
    out += payload
    return bytes(out)


def mozlz4_bytes(payload: bytes) -> bytes:
    """Wrap ``payload`` in the ``mozLz40`` container used by Firefox."""
    return MAGIC + struct.pack("<I", len(payload)) + lz4_literal_block(payload)


def write_session(profile: Path, session: Any) -> Path:
    """Write a synthetic Firefox session store into ``profile``."""
    profile.mkdir(parents=True, exist_ok=True)
    target = profile / "sessionstore.jsonlz4"
    target.write_bytes(mozlz4_bytes(json.dumps(session).encode("utf-8")))
    return target


SESSION = {
    "windows": [
        {
            "tabs": [
                {"entries": [{"url": "https://alpha.example/", "title": "Alpha"}], "index": 1},
                {
                    "entries": [
                        {"url": "https://beta.example/one", "title": "Beta one"},
                        {"url": "https://beta.example/two", "title": "Beta two"},
                    ],
                    "index": 2,
                },
                {"entries": [{"url": "about:newtab", "title": "New tab"}], "index": 1},
                {"entries": [{"url": "about:blank", "title": ""}], "index": 1},
                {"entries": [{"url": "https://alpha.example/#section", "title": "Alpha anchor"}], "index": 1},
            ]
        }
    ]
}
