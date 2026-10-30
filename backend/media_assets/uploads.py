"""A bounded memory-only multipart path, without global form parser overrides."""

import re
from email import policy
from email.parser import BytesParser
from io import BytesIO
from typing import Any

from django.core.files.uploadedfile import SimpleUploadedFile, UploadedFile
from django.core.files.uploadhandler import FileUploadHandler
from django.http import HttpRequest
from rest_framework.exceptions import ParseError
from rest_framework.parsers import MultiPartParser

from media_assets.exceptions import ImageError


class BoundedImageHandler(FileUploadHandler):
    def __init__(self, request: HttpRequest, maximum: int) -> None:
        super().__init__(request)
        self.maximum = maximum
        self.buffer = BytesIO()
        self.files = 0

    def new_file(self, *args: Any, **kwargs: Any) -> None:
        super().new_file(*args, **kwargs)
        self.files += 1
        if self.files > 1:
            raise ImageError(400, "INVALID_REQUEST")

    def receive_data_chunk(self, raw_data: bytes, start: int) -> None:
        if start + len(raw_data) > self.maximum:
            raise ImageError(413, "PAYLOAD_TOO_LARGE")
        self.buffer.write(raw_data)

    def file_complete(self, file_size: int) -> UploadedFile:
        return SimpleUploadedFile(
            "image", self.buffer.getvalue(), self.content_type or "application/octet-stream"
        )


def read_image(request: HttpRequest, maximum: int) -> bytes:
    raw = request.read(maximum + 65537)
    if len(raw) > maximum + 65536:
        raise ImageError(413, "PAYLOAD_TOO_LARGE")
    if request.content_type != "multipart/form-data":
        raise ImageError(415, "UNSUPPORTED_MEDIA_TYPE")
    boundary = (request.content_params or {}).get("boundary", "")
    if not re.fullmatch(r"[A-Za-z0-9'()+_,./:=?-]{1,70}", boundary):
        raise ImageError(400, "INVALID_REQUEST")
    # Reject excessive parts before allocating an email tree; the file can contain arbitrary bytes.
    separator = b"--" + boundary.encode("ascii")
    if raw.count(separator) > 18:
        raise ImageError(400, "INVALID_REQUEST")
    prefix = (
        b'Content-Type: multipart/form-data; boundary="'
        + boundary.encode("ascii")
        + b'"\r\nMIME-Version: 1.0\r\n\r\n'
    )
    message = BytesParser(policy=policy.default).parsebytes(prefix + raw)
    if not message.is_multipart() or message.defects:
        raise ImageError(400, "INVALID_REQUEST")
    parts = list(message.iter_parts())
    if (
        len(parts) != 1
        or parts[0].is_multipart()
        or parts[0].defects
        or parts[0].get_content_disposition() != "form-data"
        or parts[0].get_param("name", header="content-disposition") != "image"
        or parts[0].get_filename() is None
    ):
        raise ImageError(400, "INVALID_REQUEST")
    handler = BoundedImageHandler(request, maximum)
    request.upload_handlers = [handler]
    parsed = None
    try:
        parsed = MultiPartParser().parse(
            BytesIO(raw),
            request.META.get("CONTENT_TYPE"),
            {"request": request, "encoding": "utf-8"},
        )
        if parsed.data or set(parsed.files) != {"image"} or len(parsed.files.getlist("image")) != 1:
            raise ImageError(400, "INVALID_REQUEST")
        image = parsed.files["image"]
        if not isinstance(image, UploadedFile):
            raise ImageError(400, "INVALID_REQUEST")
        data = image.read(maximum + 1)
        if not isinstance(data, bytes):
            raise ImageError(400, "INVALID_REQUEST")
        if len(data) > maximum:
            raise ImageError(413, "PAYLOAD_TOO_LARGE")
        return data
    except ParseError:
        raise ImageError(400, "INVALID_REQUEST") from None
    finally:
        if parsed is not None:
            for values in parsed.files.lists():
                for uploaded in values[1]:
                    uploaded.close()
        handler.buffer.close()
