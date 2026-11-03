"""Immutable, bounded S3 objects behind the existing private image API."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from functools import lru_cache
from time import monotonic
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from botocore.parsers import ResponseParserError

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

from media_assets.configuration import S3Configuration, s3_configuration
from media_assets.exceptions import ImageError
from media_assets.storage import KEY_PATTERN, MAX_OBJECT_BYTES, StoredObject


@lru_cache(maxsize=1)
def get_s3_client(region: str) -> S3Client:
    configuration = Config(
        connect_timeout=2, read_timeout=4,
        retries={"mode": "standard", "total_max_attempts": 1},
        # Runtime botocore 1.43 supports this option; its config.pyi omits it.
        # The real SDK endpoint-override test protects this security boundary.
        ignore_configured_endpoint_urls=True,  # type: ignore[call-arg]
    )
    return boto3.client("s3", region_name=region, config=configuration)


def unavailable() -> ImageError:
    return ImageError(503, "STORAGE_UNAVAILABLE")


def error_code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))


class S3Storage:
    def __init__(self, configuration: S3Configuration | None = None) -> None:
        try:
            self.configuration = configuration or s3_configuration()
            self.client = get_s3_client(self.configuration.region)
        except (ValueError, BotoCoreError, ClientError, OSError, ResponseParserError):
            raise unavailable() from None

    def _key(self, key: str) -> str:
        if type(key) is not str or not KEY_PATTERN.fullmatch(key):
            raise unavailable()
        return self.configuration.prefix + key

    def _matches(self, key: str, digest: str) -> bool:
        try:
            return hashlib.sha256(self.read(key)).hexdigest() == digest
        except ImageError:
            return False

    def put_if_absent(self, key: str, data: bytes, digest: str) -> None:
        object_key = self._key(key)
        if len(data) > MAX_OBJECT_BYTES or hashlib.sha256(data).hexdigest() != digest:
            raise unavailable()
        for attempt in range(2):
            try:
                self.client.put_object(
                    Bucket=self.configuration.bucket, Key=object_key, Body=data,
                    ExpectedBucketOwner=self.configuration.owner,
                    IfNoneMatch="*", ServerSideEncryption="AES256",
                )
                return
            except ClientError as error:
                code = error_code(error)
                if code == "ConditionalRequestConflict" and attempt == 0:
                    continue
                status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
                ambiguous = code in {"PreconditionFailed", "ConditionalRequestConflict"} or status >= 500
                if ambiguous and self._matches(key, digest):
                    return
                raise unavailable() from None
            except (BotoCoreError, OSError, ValueError, ResponseParserError):
                if self._matches(key, digest):
                    return
                raise unavailable() from None

    def read(self, key: str) -> bytes:
        object_key = self._key(key)
        try:
            response = self.client.get_object(
                Bucket=self.configuration.bucket, Key=object_key,
                ExpectedBucketOwner=self.configuration.owner, ChecksumMode="ENABLED",
            )
            body = response["Body"]
            try:
                length = response.get("ContentLength")
                if type(length) is not int or not 0 <= length <= MAX_OBJECT_BYTES:
                    raise unavailable()
                deadline = monotonic() + 4
                content = bytearray()
                while True:
                    if monotonic() >= deadline:
                        raise unavailable()
                    chunk = body.read(min(64 * 1024, MAX_OBJECT_BYTES + 1 - len(content)))
                    if monotonic() >= deadline:
                        raise unavailable()
                    if not chunk:
                        break  # EOF also completes SDK length/checksum verification.
                    content.extend(chunk)
                    if len(content) > MAX_OBJECT_BYTES or len(content) > length:
                        raise unavailable()
                if len(content) != length:
                    raise unavailable()
                return bytes(content)
            finally:
                body.close()
        except ClientError as error:
            if error_code(error) == "NoSuchKey":
                raise ImageError(404, "NOT_FOUND") from None
            raise unavailable() from None
        except (BotoCoreError, OSError, ValueError, ResponseParserError):
            raise unavailable() from None

    def delete(self, key: str) -> None:
        object_key = self._key(key)
        try:
            self.client.delete_object(
                Bucket=self.configuration.bucket, Key=object_key,
                ExpectedBucketOwner=self.configuration.owner,
            )
        except ClientError as error:
            if error_code(error) != "NoSuchKey":
                raise unavailable() from None
        except (BotoCoreError, OSError, ValueError, ResponseParserError):
            raise unavailable() from None

    def list_page(self, cursor: str | None = None, limit: int = 100,
                  ) -> tuple[list[StoredObject], str | None]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise unavailable()
        start = self._key(cursor) if cursor is not None else self.configuration.prefix
        try:
            response = self.client.list_objects_v2(
                Bucket=self.configuration.bucket, Prefix=self.configuration.prefix,
                ExpectedBucketOwner=self.configuration.owner, StartAfter=start, MaxKeys=limit,
            )
        except (BotoCoreError, ClientError, OSError, ValueError, ResponseParserError):
            raise unavailable() from None
        truncated = response.get("IsTruncated")
        entries = response.get("Contents", [])
        if type(truncated) is not bool or len(entries) > limit:
            raise unavailable()
        rows = []
        previous = cursor or ""
        for entry in entries:
            full_key = entry.get("Key")
            modified = entry.get("LastModified")
            if (type(full_key) is not str or not full_key.startswith(self.configuration.prefix)
                    or not isinstance(modified, datetime) or modified.utcoffset() is None):
                raise unavailable()
            key = full_key[len(self.configuration.prefix):]
            self._key(key)
            if key <= previous:
                raise unavailable()
            rows.append(StoredObject(key, modified.astimezone(UTC)))
            previous = key
        if truncated and not rows:
            raise unavailable()
        return rows, rows[-1].key if truncated else None

    def sweep_temporary(self, before: datetime) -> int:
        if before.utcoffset() is None:
            raise unavailable()
        return 0  # PutObject is atomic; no local temporary or multipart objects.
