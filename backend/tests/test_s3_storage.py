"""Real S3 request signing/parsing, intercepted before any network transport."""
import base64
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from urllib.parse import parse_qs, urlsplit

import boto3
import pytest
from botocore.awsrequest import AWSResponse
from botocore.exceptions import ReadTimeoutError

from media_assets.exceptions import ImageError

KEY = "00000000000000000000000000000001.jpg"
DIGEST = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
OWNER = "123456789012"


class Raw(BytesIO):
    def stream(self, amt: int = 1024, decode_content: bool = False) -> Any:
        while chunk := self.read(amt):
            yield chunk


class Wire:
    def __init__(self) -> None:
        self.responses: deque[Any] = deque()
        self.requests: list[Any] = []
        self.raws: list[Raw] = []

    def add(self, status: int, body: bytes = b"", headers: dict[str, str] | None = None) -> None:
        self.responses.append((status, body, headers or {}))

    def error(self, status: int, code: str) -> None:
        self.add(status, f"<Error><Code>{code}</Code><Message>NEVER-LOG-THIS</Message></Error>".encode())

    def send(self, request: Any, **kwargs: Any) -> AWSResponse:
        self.requests.append(request)
        assert self.responses, "Unexpected SDK request; real network is forbidden"
        item = self.responses.popleft()
        if isinstance(item, Exception):
            raise item
        status, body, headers = item
        raw = Raw(body)
        self.raws.append(raw)
        return AWSResponse(request.url, status, headers, raw)


@pytest.fixture
def s3(settings: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    from media_assets.s3_storage import get_s3_client
    from media_assets.storage import get_storage

    settings.FITLOG_ENV = "production"
    settings.PRIVATE_MEDIA_BACKEND = "s3"
    settings.PRIVATE_MEDIA_BUCKET = "fitlog-test-private"
    settings.PRIVATE_MEDIA_EXPECTED_OWNER = OWNER
    settings.PRIVATE_MEDIA_REGION = "ap-northeast-1"
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("AWS_ENDPOINT_URL_S3", "http://example.invalid")
    session = boto3.Session(aws_access_key_id="testing", aws_secret_access_key="testing")
    wire = Wire()
    # before-send may return AWSResponse; botocore-stubs models all events as None.
    session.events.register("before-send.s3.*", wire.send)  # type: ignore[arg-type]
    monkeypatch.setattr(boto3, "DEFAULT_SESSION", session)
    get_s3_client.cache_clear()
    try:
        yield get_storage(), wire
        assert not wire.responses, "A required SDK operation was skipped"
    finally:
        get_s3_client.cache_clear()


def test_put_signs_conditional_owner_encrypted_request(s3: Any) -> None:
    store, wire = s3
    wire.add(200)
    store.put_if_absent(KEY, b"abc", DIGEST)
    r = wire.requests[0]
    assert r.method == "PUT"
    assert urlsplit(r.url).scheme == "https"
    assert urlsplit(r.url).netloc == "fitlog-test-private.s3.ap-northeast-1.amazonaws.com"
    assert urlsplit(r.url).path == "/images/" + KEY
    assert r.headers["If-None-Match"] == b"*"
    assert r.headers["x-amz-expected-bucket-owner"] == OWNER.encode()
    assert r.headers["x-amz-server-side-encryption"] == b"AES256"


@pytest.mark.parametrize("status,code", [(412, "PreconditionFailed"), (500, "InternalError")])
def test_put_reconciles_only_identical_real_bytes(s3: Any, status: int, code: str) -> None:
    store, wire = s3
    wire.error(status, code)
    wire.add(200, b"abc", {"content-length": "3"})
    store.put_if_absent(KEY, b"abc", DIGEST)
    assert [r.method for r in wire.requests] == ["PUT", "GET"]
    assert wire.raws[-1].closed


def test_put_conflict_retries_once_and_does_not_overwrite(s3: Any) -> None:
    store, wire = s3
    wire.error(409, "ConditionalRequestConflict")
    wire.add(200)
    store.put_if_absent(KEY, b"abc", DIGEST)
    assert [r.method for r in wire.requests] == ["PUT", "PUT"]
    assert all(r.headers["If-None-Match"] == b"*" for r in wire.requests)


def test_second_conflict_and_different_content_fail_without_more_writes(s3: Any) -> None:
    store, wire = s3
    wire.error(409, "ConditionalRequestConflict")
    wire.error(409, "ConditionalRequestConflict")
    wire.add(200, b"xyz", {"content-length": "3"})
    with pytest.raises(ImageError) as e:
        store.put_if_absent(KEY, b"abc", DIGEST)
    assert e.value.status == 503
    assert [r.method for r in wire.requests] == ["PUT", "PUT", "GET"]


def test_timed_out_put_is_success_only_after_digest_readback(s3: Any) -> None:
    store, wire = s3
    wire.responses.append(ReadTimeoutError(endpoint_url="https://example.invalid"))
    wire.add(200, b"abc", {"content-length": "3"})
    store.put_if_absent(KEY, b"abc", DIGEST)
    assert [r.method for r in wire.requests] == ["PUT", "GET"]


@pytest.mark.parametrize("status,code,want", [(404, "NoSuchKey", 404), (403, "AccessDenied", 503)])
def test_read_distinguishes_missing_from_permission_failure(s3: Any, status: int, code: str, want: int) -> None:
    store, wire = s3
    wire.error(status, code)
    with pytest.raises(ImageError) as e:
        store.read(KEY)
    assert e.value.status == want
    assert "NEVER-LOG-THIS" not in str(e.value)
    assert len(wire.requests) == 1


@pytest.mark.parametrize("body,length", [(b"abc", "4"), (b"x", str(5 * 1024 * 1024 + 1))])
def test_incomplete_or_oversized_stream_is_closed_and_rejected(s3: Any, body: bytes, length: str) -> None:
    store, wire = s3
    wire.add(200, body, {"content-length": length})
    with pytest.raises(ImageError) as e:
        store.read(KEY)
    assert e.value.status == 503
    assert wire.raws[-1].closed


def test_read_reaches_eof_and_verifies_checksum(s3: Any) -> None:
    store, wire = s3
    checksum = base64.b64encode(bytes.fromhex(DIGEST)).decode()
    wire.add(200, b"abc", {"content-length": "3", "x-amz-checksum-sha256": checksum})
    assert store.read(KEY) == b"abc"
    assert wire.raws[-1].closed


def test_delete_missing_is_idempotent(s3: Any) -> None:
    store, wire = s3
    wire.add(204)
    wire.add(204)
    store.delete(KEY)
    store.delete(KEY)
    assert [r.method for r in wire.requests] == ["DELETE", "DELETE"]
    assert all(r.headers["x-amz-expected-bucket-owner"] == OWNER.encode() for r in wire.requests)


def test_bad_key_digest_and_limit_never_reach_transport(s3: Any) -> None:
    store, wire = s3
    calls: list[Callable[[], object]] = [lambda: store.read("../escape"), lambda: store.put_if_absent(KEY, b"abc", "0" * 64), lambda: store.list_page(None, 1001)]
    for call in calls:
        with pytest.raises(ImageError):
            call()
    assert wire.requests == []


def listing(first: int, stop: int, truncated: bool) -> bytes:
    rows = "".join(f"<Contents><Key>images/{i:032x}.jpg</Key><LastModified>2026-01-01T00:00:00.000Z</LastModified><Size>3</Size><ETag>etag</ETag><StorageClass>STANDARD</StorageClass></Contents>" for i in range(first, stop))
    return (f'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><Name>fitlog-test-private</Name><Prefix>images/</Prefix><MaxKeys>1000</MaxKeys><KeyCount>{stop-first}</KeyCount><IsTruncated>{str(truncated).lower()}</IsTruncated>{rows}</ListBucketResult>').encode()


def test_listing_crosses_thousand_key_boundary_without_duplicates(s3: Any) -> None:
    store, wire = s3
    wire.add(200, listing(1, 1001, True))
    wire.add(200, listing(1001, 1002, False))
    rows, cursor = store.list_page(None, 1000)
    assert len(rows) == 1000 and rows[0].key == KEY
    assert cursor == "000000000000000000000000000003e8.jpg"
    assert rows[0].modified_at == datetime(2026, 1, 1, tzinfo=UTC)
    last, final = store.list_page(cursor, 1000)
    assert [x.key for x in last] == ["000000000000000000000000000003e9.jpg"]
    assert final is None
    query = parse_qs(urlsplit(wire.requests[-1].url).query)
    assert query["start-after"] == ["images/000000000000000000000000000003e8.jpg"]


def test_sdk_ignores_endpoint_override_and_has_finite_attempts(s3: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    store, wire = s3
    assert store.client.meta.config.connect_timeout == 2
    assert store.client.meta.config.read_timeout == 4
    assert store.client.meta.config.retries["total_max_attempts"] == 1
    wire.error(503, "ServiceUnavailable")
    with pytest.raises(ImageError):
        store.read(KEY)
    assert len(wire.requests) == 1


def test_s3_has_no_local_temporary_objects(s3: Any) -> None:
    store, wire = s3
    assert store.sweep_temporary(datetime.now(UTC)) == 0
    assert wire.requests == []


def test_checksum_mismatch_closes_stream(s3: Any) -> None:
    store, wire = s3
    wire.add(200, b"xyz", {"content-length": "3", "x-amz-checksum-sha256": base64.b64encode(bytes.fromhex(DIGEST)).decode()})
    with pytest.raises(ImageError) as error:
        store.read(KEY)
    assert error.value.status == 503 and wire.raws[-1].closed


def test_stream_deadline_stops_even_successful_slow_chunks(s3: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    store, wire = s3
    ticks = iter([0.0, 0.1, 4.1])
    monkeypatch.setattr("media_assets.s3_storage.monotonic", lambda: next(ticks))
    wire.add(200, b"abc", {"content-length": "3"})
    with pytest.raises(ImageError) as error:
        store.read(KEY)
    assert error.value.status == 503 and wire.raws[-1].closed


@pytest.mark.parametrize("xml", [
    listing(1, 2, False).replace(b"images/", b"outside/"),
    listing(1, 2, False).replace(KEY.encode(), b"bad.jpg"),
    listing(1, 2, False).replace(b"2026-01-01T00:00:00.000Z", b"2026-01-01T00:00:00"),
    listing(1, 1, True),
    listing(1, 3, False).replace(b"00000000000000000000000000000002.jpg", KEY.encode()),
])
def test_invalid_listing_fails_closed(s3: Any, xml: bytes) -> None:
    store, wire = s3
    wire.add(200, xml)
    with pytest.raises(ImageError) as error:
        store.list_page()
    assert error.value.status == 503


def test_put_permission_failure_does_not_read_back(s3: Any) -> None:
    store, wire = s3
    wire.error(403, "AccessDenied")
    with pytest.raises(ImageError) as error:
        store.put_if_absent(KEY, b"abc", DIGEST)
    assert error.value.status == 503
    assert [r.method for r in wire.requests] == ["PUT"]


def test_factory_initialization_failure_is_safe(settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from botocore.exceptions import NoCredentialsError

    from media_assets.s3_storage import get_s3_client
    from media_assets.storage import get_storage
    settings.FITLOG_ENV = "production"
    settings.PRIVATE_MEDIA_BACKEND = "s3"
    settings.PRIVATE_MEDIA_BUCKET = "fitlog-test-private"
    settings.PRIVATE_MEDIA_EXPECTED_OWNER = OWNER
    settings.PRIVATE_MEDIA_REGION = "ap-northeast-1"
    def fail(*args: Any, **kwargs: Any) -> Any:
        raise NoCredentialsError()
    monkeypatch.setattr(boto3, "client", fail)
    get_s3_client.cache_clear()
    with pytest.raises(ImageError) as error:
        get_storage()
    assert error.value.status == 503 and error.value.code == "STORAGE_UNAVAILABLE"


def test_get_malformed_timestamp_is_safe_storage_failure(s3: Any) -> None:
    store, wire = s3
    wire.add(200, b"abc", {"content-length": "3", "last-modified": "PRIVATE-not-a-date"})
    with pytest.raises(ImageError) as error:
        store.read(KEY)
    assert error.value.status == 503 and error.value.code == "STORAGE_UNAVAILABLE"
    assert "PRIVATE" not in str(error.value)


def test_list_malformed_timestamp_is_safe_storage_failure(s3: Any) -> None:
    store, wire = s3
    wire.add(200, listing(1, 2, False).replace(b"2026-01-01T00:00:00.000Z", b"PRIVATE-not-a-date"))
    with pytest.raises(ImageError) as error:
        store.list_page()
    assert error.value.status == 503 and error.value.code == "STORAGE_UNAVAILABLE"
    assert "PRIVATE" not in str(error.value)


def test_list_malformed_xml_is_safe_storage_failure(s3: Any) -> None:
    store, wire = s3
    wire.add(200, b"<ListBucketResult><PRIVATE-unclosed>")
    with pytest.raises(ImageError) as error:
        store.list_page()
    assert error.value.status == 503 and error.value.code == "STORAGE_UNAVAILABLE"
    assert "PRIVATE" not in str(error.value)
