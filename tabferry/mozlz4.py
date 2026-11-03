"""Read Mozilla's ``mozLz40`` container (an LZ4 block with a small header).

Firefox writes its session store as ``sessionstore.jsonlz4``: the 8-byte
magic ``mozLz40\\0``, a 4-byte little-endian uncompressed size, then one raw
LZ4 block. Only decompression is implemented here — that is all TabFerry
needs, and it keeps the project dependency-free.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any, Union

MAGIC = b"mozLz40\0"


class MozLz4Error(ValueError):
    """Raised when a file is not a valid ``mozLz40`` payload."""


def decompress(data: bytes) -> bytes:
    """Decompress a complete ``mozLz40`` byte string."""
    if not data.startswith(MAGIC):
        raise MozLz4Error("not a mozLz4 file (bad magic)")
    if len(data) < 12:
        raise MozLz4Error("truncated mozLz4 header")
    (expected,) = struct.unpack("<I", data[8:12])
    out = _decompress_lz4_block(data[12:])
    if len(out) != expected:
        raise MozLz4Error(f"size mismatch: header says {expected}, got {len(out)}")
    return out


def _decompress_lz4_block(src: bytes) -> bytes:
    dst = bytearray()
    i = 0
    n = len(src)
    while i < n:
        token = src[i]
        i += 1

        literals = token >> 4
        if literals == 15:
            while True:
                if i >= n:
                    raise MozLz4Error("truncated literal length")
                extra = src[i]
                i += 1
                literals += extra
                if extra != 255:
                    break
        if literals:
            if i + literals > n:
                raise MozLz4Error("truncated literals")
            dst += src[i : i + literals]
            i += literals

        if i >= n:
            break

        if i + 2 > n:
            raise MozLz4Error("truncated match offset")
        offset = src[i] | (src[i + 1] << 8)
        i += 2
        if offset == 0 or offset > len(dst):
            raise MozLz4Error("invalid match offset")

        match_len = token & 0x0F
        if match_len == 15:
            while True:
                if i >= n:
                    raise MozLz4Error("truncated match length")
                extra = src[i]
                i += 1
                match_len += extra
                if extra != 255:
                    break
        match_len += 4

        start = len(dst) - offset
        for k in range(match_len):
            dst.append(dst[start + k])

    return bytes(dst)


def loads(data: bytes) -> Any:
    """Decompress and parse the JSON payload."""
    return json.loads(decompress(data).decode("utf-8", "replace"))


def load(path: Union[str, Path]) -> Any:
    """Read and parse a ``.jsonlz4`` file."""
    return loads(Path(path).read_bytes())
