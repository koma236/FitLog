"""Synthetic image oracles: FL-05 design §4/11.6 and accepted Low mode table."""
import hashlib
import struct
import subprocess
import sys
import zlib
from io import BytesIO
from typing import Any

import pytest
from PIL import Image, PngImagePlugin

from media_assets.exceptions import ImageError
from media_assets.processing import normalize

LIMIT = 5 * 1024 * 1024


def encoded(image: Image.Image, format: str = "PNG", **options: Any) -> bytes:
    output = BytesIO()
    image.save(output, format=format, **options)
    return output.getvalue()


def assert_image_error(raw: bytes, status: int, code: str, limit: int = LIMIT) -> None:
    with pytest.raises(ImageError) as caught:
        normalize(raw, limit)
    assert (caught.value.status, caught.value.code) == (status, code)


def test_orientation_six_uses_fixed_coordinates_and_discards_all_metadata() -> None:
    image = Image.new("RGB", (3, 2))
    # Row major original: red, green, blue / yellow, cyan, magenta.
    image.putdata([(255, 0, 0), (0, 255, 0), (0, 0, 255),
                   (255, 255, 0), (0, 255, 255), (255, 0, 255)])
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "synthetic private description"
    exif[34853] = {1: "N", 2: (1, 2, 3)}
    info = PngImagePlugin.PngInfo()
    info.add_text("private", "synthetic private text")
    info.add_itxt("XML:com.adobe.xmp", "synthetic xmp")
    raw = encoded(image, exif=exif, pnginfo=info, icc_profile=b"synthetic icc")
    result = normalize(raw, LIMIT)
    assert (result.width, result.height, result.content_type) == (2, 3, "image/png")
    assert result.digest == hashlib.sha256(result.data).hexdigest()
    with Image.open(BytesIO(result.data)) as decoded:
        assert list(decoded.get_flattened_data()) == [
            (255, 255, 0), (255, 0, 0), (0, 255, 255),
            (0, 255, 0), (255, 0, 255), (0, 0, 255),
        ]
        assert decoded.info == {}
        assert dict(decoded.getexif()) == {}


@pytest.mark.parametrize("mode", ["RGBA", "LA", "P", "L", "RGB"])
def test_transparency_survives_all_accepted_modes(mode: str) -> None:
    image = Image.new(mode, (3, 1))
    options: dict[str, Any] = {}
    if mode == "RGBA":
        image.putdata([(20, 30, 40, 0), (50, 60, 70, 128), (80, 90, 100, 255)])
        expected = [(20, 30, 40, 0), (50, 60, 70, 128), (80, 90, 100, 255)]
    elif mode == "LA":
        image.putdata([(20, 0), (50, 128), (80, 255)])
        expected = [(20, 20, 20, 0), (50, 50, 50, 128), (80, 80, 80, 255)]
    elif mode == "P":
        image.putpalette([20, 30, 40, 50, 60, 70, 80, 90, 100] + [0] * 759)
        image.putdata([0, 1, 2])
        options["transparency"] = bytes([0, 128, 255])
        expected = [(20, 30, 40, 0), (50, 60, 70, 128), (80, 90, 100, 255)]
    elif mode == "L":
        image.putdata([20, 50, 80])
        options["transparency"] = 50
        expected = [(20, 20, 20, 255), (50, 50, 50, 0), (80, 80, 80, 255)]
    else:
        image.putdata([(20, 30, 40), (50, 60, 70), (80, 90, 100)])
        options["transparency"] = (50, 60, 70)
        expected = [(20, 30, 40, 255), (50, 60, 70, 0), (80, 90, 100, 255)]
    result = normalize(encoded(image, **options), LIMIT)
    with Image.open(BytesIO(result.data)) as decoded:
        assert decoded.mode == "RGBA"
        assert list(decoded.get_flattened_data()) == expected
        assert decoded.info == {}


@pytest.mark.parametrize("mode", ["1", "L", "P", "RGB"])
def test_opaque_png_is_rgb(mode: str) -> None:
    result = normalize(encoded(Image.new(mode, (2, 1))), LIMIT)
    with Image.open(BytesIO(result.data)) as decoded:
        assert decoded.mode == "RGB"
        assert list(decoded.get_flattened_data()) == [(0, 0, 0), (0, 0, 0)]


@pytest.mark.parametrize("mode,color", [("RGB", (240, 20, 20)), ("CMYK", (0, 255, 255, 0))])
def test_jpeg_is_rgb_stripped_and_lossy_pixel_tolerance_is_fixed(
    mode: str, color: tuple[int, ...],
) -> None:
    exif = Image.Exif()
    exif[270] = "synthetic private"
    result = normalize(encoded(Image.new(mode, (16, 16), color), "JPEG", exif=exif), LIMIT)
    assert result.content_type == "image/jpeg"
    with Image.open(BytesIO(result.data)) as decoded:
        assert decoded.mode == "RGB"
        assert dict(decoded.getexif()) == {}
        assert "exif" not in decoded.info and "icc_profile" not in decoded.info
        expected = (240, 20, 20) if mode == "RGB" else (255, 0, 0)
        pixel = decoded.getpixel((0, 0))
        assert isinstance(pixel, tuple)
        assert all(abs(a - b) <= 5 for a, b in zip(pixel, expected, strict=True))


def png_header(width: int, height: int, depth: int = 8, color: int = 2) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    ihdr = struct.pack(">IIBBBBB", width, height, depth, color, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")


@pytest.mark.parametrize("color", [0, 2, 4, 6])
def test_sixteen_bit_png_rejected_from_ihdr_even_if_decoder_mode_is_rgb(color: int) -> None:
    header = png_header(1, 1, 16, color)
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color]
    payload = zlib.compress(b"\x00" + b"\xff\xff" * channels)
    kind = b"IDAT"
    chunk = (struct.pack(">I", len(payload)) + kind + payload
             + struct.pack(">I", zlib.crc32(kind + payload)))
    raw = header[:-12] + chunk + header[-12:]
    # A valid decode distinguishes IHDR rejection from generic corruption rejection.
    with Image.open(BytesIO(raw)) as source:
        source.load()
        assert source.size == (1, 1)
        if color in (2, 6):
            assert source.mode in ("RGB", "RGBA")
    assert_image_error(raw, 415, "INVALID_IMAGE")


@pytest.mark.parametrize("size", [(20_000_001, 1), (5000, 4001)])
def test_pixel_header_limit_checked_before_full_decode(size: tuple[int, int]) -> None:
    assert_image_error(png_header(*size), 413, "PAYLOAD_TOO_LARGE")


def test_twenty_million_pixels_remain_supported() -> None:
    raw = encoded(Image.new("L", (5000, 4000), 64))
    result = normalize(raw, LIMIT)
    assert (result.width, result.height) == (5000, 4000)


def test_raw_size_boundary_and_output_size_are_separate() -> None:
    raw = encoded(Image.new("1", (32, 32), 1))
    assert_image_error(raw + b"padding", 413, "PAYLOAD_TOO_LARGE", len(raw))
    # 1-bit source is smaller than its prescribed RGB re-encoding.
    assert_image_error(raw, 413, "PAYLOAD_TOO_LARGE", len(raw))
    normalized = normalize(raw, LIMIT)
    assert normalize(raw, len(normalized.data)).data == normalized.data


@pytest.mark.parametrize("raw", [b"", b"not image", b"<svg/>", b"GIF89a", png_header(0, 1)])
def test_bad_or_disallowed_content_is_invalid(raw: bytes) -> None:
    assert_image_error(raw, 415, "INVALID_IMAGE")


def test_truncated_and_animated_png_are_rejected() -> None:
    image = Image.new("RGB", (8, 8), "red")
    raw = encoded(image)
    assert_image_error(raw[:-15], 415, "INVALID_IMAGE")
    animated = encoded(image, save_all=True, append_images=[Image.new("RGB", (8, 8), "blue")])
    assert_image_error(animated, 415, "INVALID_IMAGE")


@pytest.mark.parametrize("mode,format,orientation", [
    ("RGB", "JPEG", 1), ("CMYK", "JPEG", 6),
    ("RGBA", "PNG", 6), ("L", "PNG", 1),
])
def test_maximum_image_independent_process_peak_rss(
    mode: str, format: str, orientation: int,
) -> None:
    # Fixed 20MP fixtures and <=512MiB budget were agreed before implementation.
    program = """
import resource, sys
from io import BytesIO
from PIL import Image
from media_assets.processing import normalize
mode, fmt, orientation = sys.argv[1], sys.argv[2], int(sys.argv[3])
image = Image.new(mode, (5000, 4000))
exif = Image.Exif()
exif[274] = orientation
stream = BytesIO()
image.save(stream, format=fmt, exif=exif)
image.close()
result = normalize(stream.getvalue(), 5 * 1024 * 1024)
assert (result.width, result.height) == ((4000, 5000) if orientation == 6 else (5000, 4000))
print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
"""
    result = subprocess.run([sys.executable, "-c", program, mode, format, str(orientation)],
                            capture_output=True, text=True, check=True)
    peak = int(result.stdout.strip())
    peak_bytes = peak if sys.platform == "darwin" else peak * 1024
    assert peak_bytes <= 512 * 1024 * 1024, f"peak RSS {peak_bytes} bytes"


def test_single_frame_apng_is_still_rejected() -> None:
    base = encoded(Image.new("RGB", (4, 4), "red"))
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data)))
    actl = chunk(b"acTL", struct.pack(">II", 1, 0))
    fctl = chunk(b"fcTL", struct.pack(">IIIIIHHBB", 0, 4, 4, 0, 0, 1, 10, 0, 0))
    raw = base[:33] + actl + fctl + base[33:]
    with Image.open(BytesIO(raw)) as source:
        source.load()
        assert getattr(source, "n_frames", None) == 1
    assert_image_error(raw, 415, "INVALID_IMAGE")


def test_raw_limit_inclusive_with_metadata_heavy_source() -> None:
    info = PngImagePlugin.PngInfo()
    info.add_text("synthetic", "metadata" * 200)
    raw = encoded(Image.new("RGB", (3, 3), "red"), pnginfo=info)
    assert normalize(raw, len(raw)).width == 3
    assert_image_error(raw, 413, "PAYLOAD_TOO_LARGE", len(raw) - 1)
