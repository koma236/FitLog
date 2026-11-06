import hashlib
import unittest

from perf.images import image_fixture, pixels


class ImageTests(unittest.TestCase):
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
