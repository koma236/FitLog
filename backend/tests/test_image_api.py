"""FL-05 HTTP oracles: images never change record/body privacy or ownership."""

import struct
import zlib
from typing import Any, cast
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart

from tests.test_auth import api_client, body, signup, token
from tests.test_workouts import payload, send

pytestmark = pytest.mark.django_db(transaction=True)


def png() -> bytes:
    # PNG specification: 2x1 RGBA, transparent red then opaque blue. No product encoder.
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 1, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00\x00\x00\x00\xff\xff"))
        + chunk(b"IEND", b"")
    )


@pytest.fixture
def image_actor(settings: Any, tmp_path: Any) -> tuple[Client, str]:
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    c = api_client()
    return c, body(signup(c, token(c)))["id"]


def put_image(
    c: Client, actor: str, path: str, op: str | None = None, raw: bytes | None = None
) -> Any:
    return c.put(
        path,
        encode_multipart(
            BOUNDARY,
            {
                "image": SimpleUploadedFile(
                    "private-gps.png", png() if raw is None else raw, "image/png"
                )
            },
        ),
        content_type=MULTIPART_CONTENT,
        HTTP_X_CSRFTOKEN=token(c),
        HTTP_X_RECORD_OWNER=actor,
        HTTP_X_PROFILE_OWNER=actor,
        HTTP_X_IMAGE_OPERATION=op or str(uuid4()),
    )


def test_avatar_upload_is_normalized_and_signed(image_actor: tuple[Client, str]) -> None:
    c, owner = image_actor
    op = str(uuid4())
    response = put_image(c, owner, "/api/users/me/avatar", op)
    assert response.status_code == 200
    value = body(response)
    assert value["viewer_id"] == owner and value["avatar"]["id"] == op
    assert (value["avatar"]["width"], value["avatar"]["height"]) == (2, 1)
    assert value["avatar"]["content_type"] == "image/png"
    assert set(value["avatar"]) == {"id", "url", "expires_at", "width", "height", "content_type"}
    public = api_client().get(value["avatar"]["url"])
    assert public.status_code == 200 and public["Content-Type"] == "image/png"
    assert public["Cache-Control"] == "no-store" and public["X-Content-Type-Options"] == "nosniff"
    assert (
        c.delete(
            "/api/users/me/avatar", HTTP_X_CSRFTOKEN=token(c), HTTP_X_PROFILE_OWNER=owner
        ).status_code
        == 204
    )
    assert body(c.get("/api/users/me"))["avatar"] is None


def test_post_image_does_not_change_record_fields(image_actor: tuple[Client, str]) -> None:
    c, owner = image_actor
    record = body(send(c, owner, "POST", "/api/posts", payload()))
    key = record["id"]
    response = put_image(c, owner, "/api/posts/" + key + "/image")
    assert response.status_code == 200
    after = body(response)
    for field in [
        "note",
        "exercises",
        "energy",
        "energy_input",
        "visibility",
        "created_at",
        "updated_at",
    ]:
        assert after[field] == record[field]
    assert after["image"] is not None


def test_same_operation_replay_and_retired_identity(image_actor: tuple[Client, str]) -> None:
    from media_assets.models import ImageObject

    c, owner = image_actor
    op = str(uuid4())
    first = body(put_image(c, owner, "/api/users/me/avatar", op))["avatar"]
    replay = put_image(c, owner, "/api/users/me/avatar", op)
    assert replay.status_code == 200 and body(replay)["avatar"]["id"] == op
    assert ImageObject.objects.count() == 1
    assert put_image(c, owner, "/api/users/me/avatar").status_code == 200
    assert put_image(c, owner, "/api/users/me/avatar", op).status_code == 409
    assert ImageObject.objects.get(pk=op).state == "retired"
    assert api_client().get(first["url"]).status_code == 404


def test_foreign_and_stale_owner_cannot_change_post_image(image_actor: tuple[Client, str]) -> None:
    c, owner = image_actor
    record = body(send(c, owner, "POST", "/api/posts", payload()))
    path = "/api/posts/" + record["id"] + "/image"
    before = body(put_image(c, owner, path))
    other = api_client()
    other_id = body(signup(other, token(other), "other_image", "other-image@example.test"))["id"]
    assert put_image(other, owner, path).status_code == 409
    assert put_image(other, other_id, path).status_code == 403
    assert (
        other.delete(path, HTTP_X_CSRFTOKEN=token(other), HTTP_X_RECORD_OWNER=other_id).status_code
        == 403
    )
    after = body(c.get("/api/posts/" + record["id"]))
    assert after["image"]["id"] == before["image"]["id"]
    assert after["note"] == record["note"] and after["visibility"] == record["visibility"]
    public = body(other.get("/api/posts/" + record["id"]))
    assert public["image"]["id"] == before["image"]["id"]
    assert public["energy_input"] == {} and "visibility" not in public
    assert not {"email", "key", "digest", "actor"} & set(public["image"])
    third = api_client()
    third_id = body(signup(third, token(third), "third_image", "third-image@example.test"))["id"]
    assert put_image(third, other_id, path).status_code == 409
    assert put_image(third, third_id, path).status_code == 403
    assert body(third.get("/api/posts/" + record["id"]))["image"]["id"] == before["image"]["id"]


def test_storage_failure_preserves_old_attachment_and_same_op_resumes(
    image_actor: tuple[Client, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from media_assets.exceptions import ImageError
    from media_assets.models import ImageObject
    from media_assets.storage import LocalStorage

    c, owner = image_actor
    old = body(put_image(c, owner, "/api/users/me/avatar"))["avatar"]
    op = str(uuid4())
    original = LocalStorage.put_if_absent

    def fail(*args: Any, **kwargs: Any) -> None:
        raise ImageError(503, "STORAGE_UNAVAILABLE")

    monkeypatch.setattr(LocalStorage, "put_if_absent", fail)
    rejected = put_image(c, owner, "/api/users/me/avatar", op)
    assert rejected.status_code == 503 and body(rejected)["code"] == "STORAGE_UNAVAILABLE"
    assert body(c.get("/api/users/me"))["avatar"]["id"] == old["id"]
    assert ImageObject.objects.get(pk=op).state == "pending"
    monkeypatch.setattr(LocalStorage, "put_if_absent", original)
    assert body(put_image(c, owner, "/api/users/me/avatar", op))["avatar"]["id"] == op


def test_c_rollback_keeps_pending_and_does_not_delete_old_file(
    image_actor: tuple[Client, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from uuid import UUID

    from django.db import OperationalError

    from accounts.models import User
    from media_assets import service
    from media_assets.models import ImageCleanupJob, ImageObject
    from media_assets.processing import normalize
    from media_assets.storage import LocalStorage

    c, owner = image_actor
    old = body(put_image(c, owner, "/api/users/me/avatar"))["avatar"]
    op = uuid4()
    save = ImageObject.save

    def fail_at_attach(self: Any, *args: Any, **kwargs: Any) -> None:
        save(self, *args, **kwargs)
        if self.pk == op and self.state == "attached":
            raise OperationalError("injected final transaction failure")

    monkeypatch.setattr(ImageObject, "save", fail_at_attach)
    with pytest.raises(OperationalError):
        service.upload(
            User.objects.get(pk=owner), "avatar", UUID(owner), op, normalize(png(), 2097152)
        )
    assert ImageObject.objects.get(pk=op).state == "pending"
    assert ImageObject.objects.get(pk=old["id"]).state == "attached"
    assert not ImageCleanupJob.objects.filter(object_id=old["id"]).exists()
    assert LocalStorage().read(ImageObject.objects.get(pk=old["id"]).key)
    monkeypatch.setattr(ImageObject, "save", save)
    assert put_image(c, owner, "/api/users/me/avatar", str(op)).status_code == 200


def test_post_cascade_retires_image_and_cleanup_reconciles_late_write(
    image_actor: tuple[Client, str],
) -> None:
    import os
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone

    from media_assets.cleanup import cleanup_images
    from media_assets.models import ImageCleanupJob, ImageObject
    from media_assets.storage import LocalStorage

    c, owner = image_actor
    record = body(send(c, owner, "POST", "/api/posts", payload()))
    image = body(put_image(c, owner, "/api/posts/" + record["id"] + "/image"))["image"]
    obj = ImageObject.objects.get(pk=image["id"])
    raw = LocalStorage().read(obj.key)
    assert send(c, owner, "DELETE", "/api/posts/" + record["id"]).status_code == 204
    obj.refresh_from_db()
    assert obj.state == "retired"
    assert ImageCleanupJob.objects.get(object=obj).completed_at is not None
    LocalStorage().put_if_absent(
        obj.key, raw, obj.digest
    )  # An external late completion after cleanup.
    at = (timezone.now() - timedelta(hours=2)).timestamp()
    os.utime(settings.PRIVATE_MEDIA_ROOT / obj.key, (at, at))
    assert cleanup_images()["reconciled"] == 1
    assert not (settings.PRIVATE_MEDIA_ROOT / obj.key).exists()


@pytest.mark.parametrize(("age", "status"), [(299, 200), (300, 200), (301, 404), (-1, 404)])
def test_capability_expiry_and_opaque_payload(
    image_actor: tuple[Client, str], monkeypatch: pytest.MonkeyPatch, age: int, status: int
) -> None:
    import time

    from django.core import signing

    from media_assets.presentation import SALT

    c, owner = image_actor
    at = 1800000000
    monkeypatch.setattr(time, "time", lambda: at)
    image = body(put_image(c, owner, "/api/users/me/avatar"))["avatar"]
    signed = image["url"].rsplit("/", 1)[1]
    decoded = signing.loads(signed, salt=SALT)
    assert set(decoded) == {"id", "at"} and decoded["id"] == image["id"]
    monkeypatch.setattr(time, "time", lambda: at + age)
    response = api_client().get(image["url"])
    assert response.status_code == status
    assert response["Cache-Control"] == "no-store"
    assert api_client().get(image["url"] + "tampered").status_code == 404


def test_size_structure_csrf_and_busy_boundaries(image_actor: tuple[Client, str]) -> None:
    from media_assets.views import DECODE_SLOT

    c, owner = image_actor
    assert put_image(c, owner, "/api/users/me/avatar", raw=b"x" * 2097153).status_code == 413
    assert put_image(c, owner, "/api/users/me/avatar", raw=b"<svg/>").status_code == 415
    duplicate = encode_multipart(
        BOUNDARY,
        {"image": [SimpleUploadedFile("a.png", png()), SimpleUploadedFile("b.png", png())]},
    )
    assert (
        c.put(
            "/api/users/me/avatar",
            duplicate,
            content_type=MULTIPART_CONTENT,
            HTTP_X_CSRFTOKEN=token(c),
            HTTP_X_PROFILE_OWNER=owner,
            HTTP_X_IMAGE_OPERATION=str(uuid4()),
        ).status_code
        == 400
    )
    assert (
        c.put(
            "/api/users/me/avatar",
            b"invalid",
            content_type=MULTIPART_CONTENT,
            HTTP_X_PROFILE_OWNER=owner,
        ).status_code
        == 403
    )
    assert DECODE_SLOT.acquire(blocking=False)
    try:
        response = put_image(c, owner, "/api/users/me/avatar")
        assert response.status_code == 503 and body(response)["code"] == "IMAGE_PROCESSING_BUSY"
        assert response["Retry-After"] == "2"
    finally:
        DECODE_SLOT.release()
    assert body(c.get("/api/users/me"))["id"] == owner


def test_parallel_same_operation_creates_one_attachment(
    image_actor: tuple[Client, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Event
    from uuid import UUID

    from django.db import close_old_connections, connections

    from accounts.models import User
    from media_assets import service
    from media_assets.models import ImageObject, UserAvatar
    from media_assets.processing import normalize

    c, owner = image_actor
    rendezvous = Barrier(2)
    ready = Event()
    original = service.locked_target
    value = normalize(png(), 2097152)
    operation = uuid4()

    def stage(*args: Any, **kwargs: Any) -> Any:
        ready.set()
        rendezvous.wait(timeout=10)
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "locked_target", stage)

    def worker() -> str:
        close_old_connections()
        try:
            return str(
                service.upload(User.objects.get(pk=owner), "avatar", UUID(owner), operation, value)[
                    "avatar"
                ]["id"]
            )
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(worker)
        assert ready.wait(timeout=10)  # First immutable write committed before the replay starts.
        futures = [first, pool.submit(worker)]
        assert [future.result(timeout=20) for future in futures] == [str(operation), str(operation)]
    assert ImageObject.objects.count() == 1 and UserAvatar.objects.count() == 1
    assert body(c.get("/api/users/me"))["avatar"]["id"] == str(operation)


def test_delete_between_storage_and_attachment_does_not_resurrect_post(
    image_actor: tuple[Client, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    from threading import Event
    from uuid import UUID

    from django.db import close_old_connections, connections
    from django.utils import timezone

    from accounts.models import User
    from media_assets import service
    from media_assets.cleanup import cleanup_images
    from media_assets.exceptions import ImageError
    from media_assets.models import ImageObject
    from media_assets.processing import normalize

    c, owner = image_actor
    record = body(send(c, owner, "POST", "/api/posts", payload()))
    ready = Event()
    release = Event()
    original = service.locked_target
    operation = uuid4()
    value = normalize(png(), 5242880)

    def stage(*args: Any, **kwargs: Any) -> Any:
        ready.set()
        if not release.wait(timeout=10):
            raise AssertionError("delete barrier was not released")
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "locked_target", stage)

    def worker() -> int:
        close_old_connections()
        try:
            service.upload(User.objects.get(pk=owner), "post", UUID(record["id"]), operation, value)
            raise AssertionError("deleted post was recreated")
        except ImageError as exc:
            return exc.status
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(worker)
        try:
            assert ready.wait(timeout=10)
            assert send(c, owner, "DELETE", "/api/posts/" + record["id"]).status_code == 204
        finally:
            release.set()
        assert future.result(timeout=20) == 404
    assert c.get("/api/posts/" + record["id"]).status_code == 404
    ImageObject.objects.filter(pk=operation).update(created_at=timezone.now() - timedelta(hours=2))
    cleanup_images()
    assert ImageObject.objects.get(pk=operation).state == "retired"


def test_startup_storage_environment_truth_table(settings: Any) -> None:
    from media_assets.checks import private_storage_configuration

    for environment, allowed in [
        ("local", True),
        ("production", False),
        ("staging", False),
        ("test", False),
        ("other", False),
    ]:
        settings.FITLOG_ENV = environment
        assert (not private_storage_configuration(None)) is allowed
    settings.FITLOG_ENV = "local"
    settings.PRIVATE_MEDIA_BACKEND = "unexpected"
    assert private_storage_configuration(None)[0].id == "media_assets.E001"


def test_gc_and_active_write_never_remove_an_attached_image(
    image_actor: tuple[Client, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    from threading import Event
    from time import monotonic, sleep
    from uuid import UUID

    from django.db import close_old_connections, connections
    from django.utils import timezone

    from accounts.models import User
    from media_assets import service
    from media_assets.cleanup import cleanup_images
    from media_assets.exceptions import ImageError
    from media_assets.models import ImageObject, UserAvatar
    from media_assets.processing import normalize
    from media_assets.storage import LocalStorage

    _, owner = image_actor
    operation = uuid4()
    value = normalize(png(), 2097152)
    ImageObject.objects.create(
        id=operation,
        target_kind="avatar",
        target_uuid=owner,
        actor=owner,
        key=uuid4().hex + ".png",
        digest=value.digest,
        size=len(value.data),
        width=value.width,
        height=value.height,
        content_type=value.content_type,
        created_at=timezone.now() - timedelta(hours=2),
    )
    writing = Event()
    release = Event()
    gc_started = Event()
    gc_finished = Event()
    gc_pid: list[int] = []
    original_target = service.locked_target

    def after_collection(*args: Any, **kwargs: Any) -> Any:
        assert gc_finished.wait(timeout=10)
        return original_target(*args, **kwargs)

    monkeypatch.setattr(service, "locked_target", after_collection)
    original = LocalStorage.put_if_absent

    def paused(self: Any, *args: Any, **kwargs: Any) -> None:
        writing.set()
        if not release.wait(timeout=10):
            raise AssertionError("write barrier was not released")
        original(self, *args, **kwargs)

    monkeypatch.setattr(LocalStorage, "put_if_absent", paused)

    def writer() -> int:
        close_old_connections()
        try:
            service.upload(User.objects.get(pk=owner), "avatar", UUID(owner), operation, value)
            return 200
        except ImageError as exc:
            return exc.status
        finally:
            connections.close_all()

    def collector() -> None:
        close_old_connections()
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                gc_pid.append(cursor.fetchone()[0])
            gc_started.set()
            cleanup_images()
            gc_finished.set()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        write_future = pool.submit(writer)
        try:
            assert writing.wait(timeout=10)
            gc_future = pool.submit(collector)
            assert gc_started.wait(timeout=10)
            deadline = monotonic() + 10
            while monotonic() < deadline:
                with connections["default"].cursor() as cursor:
                    cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [gc_pid[0]])
                    row = cursor.fetchone()
                if row and row[0] == "Lock":
                    break
                sleep(0.01)
            else:
                raise AssertionError("collector never waited on the active writer DB lock")
        finally:
            release.set()
        status = write_future.result(timeout=20)
        gc_future.result(timeout=20)
    obj = ImageObject.objects.get(pk=operation)
    assert status == 409 and obj.state == "retired"
    assert not UserAvatar.objects.filter(object_id=operation).exists()
    with pytest.raises(ImageError) as missing:
        LocalStorage().read(obj.key)
    assert missing.value.status == 404


def test_development_access_logging_does_not_emit_capability_urls() -> None:
    import logging

    logger = logging.getLogger("django.server")
    assert not logger.propagate
    assert logger.handlers and all(
        isinstance(handler, logging.NullHandler) for handler in logger.handlers
    )


def test_post_deleted_after_image_commit_returns_not_found(
    image_actor: tuple[Client, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from media_assets import service
    from workouts.models import Post

    c, owner = image_actor
    record = body(send(c, owner, "POST", "/api/posts", payload()))
    original = service.response

    def deleted(*args: Any, **kwargs: Any) -> Any:
        Post.objects.get(pk=record["id"]).delete()
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "response", deleted)
    assert put_image(c, owner, "/api/posts/" + record["id"] + "/image").status_code == 404


def test_actor_disabled_after_image_commit_returns_auth_required(
    image_actor: tuple[Client, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from accounts.models import User
    from media_assets import service

    c, owner = image_actor
    original = service.response

    def disabled(*args: Any, **kwargs: Any) -> Any:
        User.objects.filter(pk=owner).update(is_active=False)
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "response", disabled)
    response = put_image(c, owner, "/api/users/me/avatar")
    assert response.status_code == 401 and body(response)["code"] == "AUTH_REQUIRED"


def test_capability_database_failure_keeps_login_cookie(
    image_actor: tuple[Client, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from django.db import OperationalError

    from media_assets.models import ImageObject

    c, owner = image_actor
    image = body(put_image(c, owner, "/api/users/me/avatar"))["avatar"]

    def offline(*args: Any, **kwargs: Any) -> Any:
        raise OperationalError("synthetic database outage")

    monkeypatch.setattr(ImageObject.objects, "filter", offline)
    response = c.get(image["url"])
    assert response.status_code == 503
    assert response["Cache-Control"] == "no-store"
    assert "sessionid" not in response.cookies


def test_large_unicode_multipart_uses_no_temporary_file_handler(
    image_actor: tuple[Client, str], monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    from django.core.files.uploadedfile import TemporaryUploadedFile

    assert settings.DATA_UPLOAD_MAX_NUMBER_FILES == 1
    assert settings.DATA_UPLOAD_MAX_NUMBER_FIELDS == 16
    c, owner = image_actor
    record = body(send(c, owner, "POST", "/api/posts", payload()))
    marker = b"note\x00" + b"a" * (5 * 1024 * 1024 - len(png()) - 17)
    extra = struct.pack(">I", len(marker)) + b"tEXt" + marker
    extra += struct.pack(">I", zlib.crc32(b"tEXt" + marker))
    raw = png()[:-12] + extra + png()[-12:]
    assert len(raw) == 5 * 1024 * 1024

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("disk upload handler must never be used")

    monkeypatch.setattr(TemporaryUploadedFile, "__init__", forbidden)
    response = c.put(
        "/api/posts/" + record["id"] + "/image",
        encode_multipart(BOUNDARY, {"image": SimpleUploadedFile("筋トレ写真.png", raw, "image/png")}),
        content_type=MULTIPART_CONTENT,
        HTTP_X_CSRFTOKEN=token(c), HTTP_X_RECORD_OWNER=owner,
        HTTP_X_IMAGE_OPERATION=str(uuid4()),
    )
    assert response.status_code == 200
    assert body(response)["image"]["width"] == 2


def test_real_twenty_mp_request_keeps_busy_and_health_independent(
    image_actor: tuple[Client, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import close_old_connections, connections

    from media_assets import views
    from media_assets.processing import normalize

    c, owner = image_actor
    second = api_client()
    second.cookies.update(c.cookies)
    entered, release = Event(), Event()
    original = normalize
    compressor = zlib.compressobj()
    compressed = b"".join(compressor.compress(b"\0" + b"\xff\0\0\xff" * 5000) for _ in range(4000))
    compressed += compressor.flush()

    def chunk(kind: bytes, value: bytes) -> bytes:
        return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value))

    raw = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 5000, 4000, 8, 6, 0, 0, 0))
    raw += chunk(b"IDAT", compressed) + chunk(b"IEND", b"")

    def paused(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        assert release.wait(timeout=10)
        return original(*args, **kwargs)

    monkeypatch.setattr(views, "normalize", paused)

    def first() -> Any:
        close_old_connections()
        try:
            return put_image(c, owner, "/api/users/me/avatar", raw=raw)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(first)
        try:
            assert entered.wait(timeout=10)
            busy = put_image(second, owner, "/api/users/me/avatar", raw=raw)
            assert busy.status_code == 503 and body(busy)["code"] == "IMAGE_PROCESSING_BUSY"
            assert busy["Retry-After"] == "2"
            assert second.get("/api/health/live").status_code == 200
            assert not future.done()
        finally:
            release.set()
        result = future.result(timeout=20)
    assert result.status_code == 200
    assert (body(result)["avatar"]["width"], body(result)["avatar"]["height"]) == (5000, 4000)
    assert second.get("/api/health/live").status_code == 200


def test_attachment_commit_ack_loss_is_recovered_by_operation(
    image_actor: tuple[Client, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from django.db import OperationalError, connection

    from media_assets.models import ImageObject, UserAvatar

    c, owner = image_actor
    operation = uuid4()
    original = cast(Any, connection)._commit
    injected = False

    def acknowledged_lost() -> None:
        nonlocal injected
        committed = UserAvatar.objects.filter(user_id=owner, object_id=operation).exists()
        original()
        if committed and not injected:
            injected = True
            raise OperationalError("synthetic lost commit acknowledgement")

    with monkeypatch.context() as patch:
        patch.setattr(connection, "_commit", acknowledged_lost)
        response = put_image(c, owner, "/api/users/me/avatar", str(operation))
    assert injected and response.status_code == 503
    assert ImageObject.objects.get(pk=operation).state == "attached"
    assert UserAvatar.objects.get(user_id=owner).object_id == ImageObject.objects.get(pk=operation).pk
    from tests.test_auth import PASSWORD

    login = c.post("/api/auth/login", {"email": "river@example.test", "password": PASSWORD}, content_type="application/json", HTTP_X_CSRFTOKEN=token(c))
    assert login.status_code == 200
    recovered = put_image(c, owner, "/api/users/me/avatar", str(operation))
    assert recovered.status_code == 200 and body(recovered)["avatar"]["id"] == str(operation)


def test_orphan_scan_does_not_hold_unrelated_attached_object_lock(
    image_actor: tuple[Client, str], monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    import os
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    from threading import Event

    from django.db import close_old_connections, connections
    from django.utils import timezone

    from media_assets.cleanup import cleanup_images
    from media_assets.models import ImageObject
    from media_assets.processing import normalize
    from media_assets.storage import LocalStorage

    c, owner = image_actor
    image = body(put_image(c, owner, "/api/users/me/avatar"))["avatar"]
    obj = ImageObject.objects.get(pk=image["id"])
    storage = LocalStorage()
    value = normalize(png(), 2097152)
    early_key, orphan = "0" * 32 + ".png", "f" * 32 + ".png"
    storage.put_if_absent(early_key, value.data, value.digest)
    storage.delete(obj.key)
    ImageObject.objects.filter(pk=obj.pk).update(key=early_key)
    storage.put_if_absent(orphan, value.data, value.digest)
    old = (timezone.now() - timedelta(hours=2)).timestamp()
    for key in (early_key, orphan):
        os.utime(settings.PRIVATE_MEDIA_ROOT / key, (old, old))
    deleting, release = Event(), Event()
    original = LocalStorage.delete

    def paused(self: Any, key: str) -> None:
        if key == orphan:
            deleting.set()
            assert release.wait(timeout=10)
        original(self, key)

    monkeypatch.setattr(LocalStorage, "delete", paused)

    def collect() -> Any:
        close_old_connections()
        try:
            return cleanup_images()
        finally:
            connections.close_all()

    def replace() -> Any:
        close_old_connections()
        try:
            return put_image(c, owner, "/api/users/me/avatar")
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        gc_future = pool.submit(collect)
        try:
            assert deleting.wait(timeout=10)
            updated = pool.submit(replace).result(timeout=5)
            assert updated.status_code == 200
            assert not gc_future.done()
        finally:
            release.set()
        assert gc_future.result(timeout=10)["reconciled"] == 1
    obj.refresh_from_db()
    assert obj.state == "retired"


@pytest.mark.parametrize("remove", [False, True])
def test_avatar_replacements_and_delete_follow_user_lock_order(
    image_actor: tuple[Client, str], monkeypatch: pytest.MonkeyPatch, remove: bool
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from time import monotonic, sleep
    from uuid import UUID

    from django.db import close_old_connections, connections

    from accounts.models import User
    from media_assets import service
    from media_assets.exceptions import ImageError
    from media_assets.models import ImageObject, UserAvatar
    from media_assets.processing import normalize

    c, owner = image_actor
    old = body(put_image(c, owner, "/api/users/me/avatar"))["avatar"]["id"]
    first_op, second_op = UUID(int=101), UUID(int=102)
    value = normalize(png(), 2097152)
    locked, second_started, release = Event(), Event(), Event()
    second_pid: list[int] = []
    original = service.locked_target

    def paused(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        if not locked.is_set():
            locked.set()
            assert release.wait(timeout=10)
        return result

    monkeypatch.setattr(service, "locked_target", paused)

    def mutate(operation: UUID, deleting: bool = False) -> None:
        close_old_connections()
        try:
            actor = User.objects.get(pk=owner)
            if operation == second_op:
                with connections["default"].cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    second_pid.append(cursor.fetchone()[0])
                second_started.set()
            if deleting:
                service.remove(actor, "avatar", UUID(owner))
            else:
                service.upload(actor, "avatar", UUID(owner), operation, value)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(mutate, first_op)
        try:
            assert locked.wait(timeout=10)
            second = pool.submit(mutate, second_op, remove)
            assert second_started.wait(timeout=10)
            deadline = monotonic() + 10
            while monotonic() < deadline:
                with connections["default"].cursor() as cursor:
                    cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [second_pid[0]])
                    row = cursor.fetchone()
                if row and row[0] == "Lock":
                    break
                sleep(0.01)
            else:
                raise AssertionError("second avatar operation never waited on the first User lock")
        finally:
            release.set()
        first.result(timeout=20)
        second.result(timeout=20)
    assert ImageObject.objects.get(pk=old).state == "retired"
    assert ImageObject.objects.get(pk=first_op).state == "retired"
    if remove:
        assert not UserAvatar.objects.filter(user_id=owner).exists()
    else:
        assert UserAvatar.objects.get(user_id=owner).object_id == second_op
        assert ImageObject.objects.get(pk=second_op).state == "attached"
    with pytest.raises(ImageError) as retired:
        service.upload(User.objects.get(pk=owner), "avatar", UUID(owner), first_op, value)
    assert retired.value.status == 409


def test_post_image_response_keeps_authoritative_social_projection(
    image_actor: tuple[Client, str],
) -> None:
    from tests.test_social_api import cid, social

    owner_client, owner = image_actor
    record = body(send(owner_client, owner, "POST", "/api/posts", payload()))
    key = record["id"]
    other = api_client()
    other_id = body(signup(other, token(other), "image_social_b", "image_social_b@example.test"))["id"]
    assert social(other, other_id, "POST", "/api/posts/" + key + "/comments", {"id": cid(901), "body": "other author"}).status_code == 201
    assert social(other, other_id, "POST", "/api/posts/" + key + "/like").status_code == 200
    before_self_like = put_image(owner_client, owner, "/api/posts/" + key + "/image")
    assert before_self_like.status_code == 200
    value = body(before_self_like)
    assert (value["comment_count"], value["like_count"], value["is_liked"]) == (1, 1, False)
    assert social(owner_client, owner, "POST", "/api/posts/" + key + "/like").status_code == 200
    after_self_like = put_image(owner_client, owner, "/api/posts/" + key + "/image")
    assert after_self_like.status_code == 200
    value = body(after_self_like)
    assert (value["comment_count"], value["like_count"], value["is_liked"]) == (1, 2, True)
    for field in ("note", "exercises", "energy", "energy_input", "visibility", "created_at", "updated_at"):
        assert value[field] == record[field]
