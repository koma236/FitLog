import hashlib
import struct
import unittest

from perf.images import SIGNATURE, chunk, image_fixture, pixels


class ImageTests(unittest.TestCase):
    def test_incomplete_zlib_stream_with_valid_chunk_crc_is_rejected(self):
        original = image_fixture(147)[0]
        result, offset = SIGNATURE, 8
        while offset < len(original):
            length = struct.unpack(">I", original[offset:offset + 4])[0]
            kind = original[offset + 4:offset + 8]
            data = original[offset + 8:offset + 8 + length]
            result += chunk(kind, data[:-4] if kind == b"IDAT" else data)
            offset += length + 12
        with self.assertRaises(ValueError):
            pixels(result)
    def test_fixed_sizes_and_pixels(self):
        for size in (147, 590, 1320):
            raw, expected = image_fixture(size)
            self.assertLessEqual(len(raw), 5 * 1024 * 1024)
            width, height, decoded = pixels(raw)
            self.assertEqual((width, height), (size, size))
            self.assertEqual(hashlib.sha256(decoded).hexdigest(), expected)

    def test_invalid_or_truncated_image_rejected(self):
        for raw in (b"", b"PNG", image_fixture(1)[0][:-12]):
            with self.assertRaises(ValueError):
                pixels(raw)
