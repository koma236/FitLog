"""Decode bounded JPEG/PNG bytes and retain pixels only."""
import hashlib
import struct
import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps

from media_assets.exceptions import ImageError

MAX_PIXELS = 20_000_000
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class NormalizedImage:
    data: bytes
    content_type: str
    width: int
    height: int
    digest: str


def _check_dimensions(width: int, height: int) -> None:
    if width < 1 or height < 1:
        raise ImageError(415, "INVALID_IMAGE")
    if width * height > MAX_PIXELS:
        raise ImageError(413, "PAYLOAD_TOO_LARGE")


def normalize(raw: bytes, max_bytes: int) -> NormalizedImage:
    if len(raw) > max_bytes:
        raise ImageError(413, "PAYLOAD_TOO_LARGE")
    # Inspect IHDR independently: Pillow can expose 16-bit RGB/RGBA as 8-bit mode.
    if raw.startswith(PNG_SIGNATURE) and len(raw) >= 33 and raw[8:16] == b"\x00\x00\x00\rIHDR":
        _check_dimensions(*struct.unpack(">II", raw[16:24]))
        if raw[24] == 16:
            raise ImageError(415, "INVALID_IMAGE")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw), formats=("JPEG", "PNG")) as probe:
                _check_dimensions(*probe.size)
                if (getattr(probe, "custom_mimetype", None) == "image/apng"
                        or getattr(probe, "is_animated", False)
                        or getattr(probe, "n_frames", 1) != 1):
                    raise ImageError(415, "INVALID_IMAGE")
                probe.verify()
            with Image.open(BytesIO(raw), formats=("JPEG", "PNG")) as source:
                source.load()
                image_format = source.format
                ImageOps.exif_transpose(source, in_place=True)
                has_alpha = source.mode in ("RGBA", "LA") or "transparency" in source.info
                mode = "RGBA" if image_format == "PNG" and has_alpha else "RGB"
                with source.convert(mode) as converted:
                    size = converted.size
                    # A new pixel canvas does not inherit EXIF/ICC/XMP/text dictionaries.
                    with Image.new(mode, size) as clean:
                        clean.paste(converted)
                        output = BytesIO()
                        if image_format == "JPEG":
                            clean.save(output, format="JPEG", quality=85,
                                       optimize=False, progressive=False)
                        else:
                            clean.save(output, format="PNG", compress_level=6, optimize=False)
                        data = output.getvalue()
        if len(data) > max_bytes:
            raise ImageError(413, "PAYLOAD_TOO_LARGE")
        return NormalizedImage(
            data=data, content_type="image/jpeg" if image_format == "JPEG" else "image/png",
            width=size[0], height=size[1], digest=hashlib.sha256(data).hexdigest(),
        )
    except MemoryError:
        raise ImageError(503, "IMAGE_PROCESSING_BUSY") from None
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombWarning,
            Image.DecompressionBombError):
        raise ImageError(415, "INVALID_IMAGE") from None
