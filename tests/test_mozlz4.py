from __future__ import annotations

import struct
import unittest

from tabferry import mozlz4
from tests.helpers import lz4_literal_block


class MozLz4Tests(unittest.TestCase):
    def test_roundtrip_small(self):
        payload = b'{"windows": []}'
        data = b"mozLz40\0" + struct.pack("<I", len(payload)) + lz4_literal_block(payload)
        self.assertEqual(mozlz4.decompress(data), payload)

    def test_roundtrip_large(self):
        payload = b"x" * 5000
        data = b"mozLz40\0" + struct.pack("<I", len(payload)) + lz4_literal_block(payload)
        self.assertEqual(mozlz4.decompress(data), payload)

    def test_bad_magic(self):
        with self.assertRaises(mozlz4.MozLz4Error):
            mozlz4.decompress(b"not-mozlz4")

    def test_size_mismatch(self):
        payload = b"abc"
        data = b"mozLz40\0" + struct.pack("<I", 99) + lz4_literal_block(payload)
        with self.assertRaises(mozlz4.MozLz4Error):
            mozlz4.decompress(data)

    def test_truncated_header(self):
        with self.assertRaises(mozlz4.MozLz4Error):
            mozlz4.decompress(b"mozLz40\0")


if __name__ == "__main__":
    unittest.main()
