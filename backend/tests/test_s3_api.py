"""Storage factory integration with real PostgreSQL and real botocore parsing."""
import time
from typing import Any
from uuid import uuid4

import pytest
from django.core import signing

from media_assets.models import ImageObject, UserAvatar
from media_assets.presentation import SALT
from tests.test_auth import api_client, body, signup, token
from tests.test_image_api import image_actor as image_actor
from tests.test_image_api import put_image
from tests.test_s3_storage import listing
from tests.test_s3_storage import s3 as s3
from tests.test_workouts import payload, send

pytestmark = pytest.mark.django_db(transaction=True)


def test_s3_upload_content_expiry_and_failed_replacement(image_actor: Any, s3: Any) -> None:
    client, owner = image_actor
    _, wire = s3
    wire.add(200)
    first = put_image(client, owner, "/api/users/me/avatar")
    assert first.status_code == 200
    avatar = body(first)["avatar"]
    row = ImageObject.objects.get(pk=avatar["id"])
    assert row.state == "attached" and row.written_at is not None
    wire.add(200, b"stored-image", {"content-length": "12"})
    response = api_client().get(avatar["url"])
    assert response.status_code == 200 and response.content == b"stored-image"
    assert response["Cache-Control"] == "no-store"
    old_token = signing.dumps({"id": avatar["id"], "at": int(time.time()) - 301}, salt=SALT)
    assert api_client().get("/api/media/content/" + old_token).status_code == 404
    operation = str(uuid4())
    wire.error(500, "InternalError")
    wire.error(404, "NoSuchKey")
    failed = put_image(client, owner, "/api/users/me/avatar", operation)
    assert failed.status_code == 503 and body(failed)["code"] == "STORAGE_UNAVAILABLE"
    assert str(UserAvatar.objects.get(user_id=owner).object_id) == avatar["id"]
    pending = ImageObject.objects.get(pk=operation)
    assert pending.state == "pending" and pending.written_at is None
    assert ImageObject.objects.get(pk=avatar["id"]).state == "attached"
    # Same operation safely resumes through the factory; retiring the old row deletes it.
    wire.add(200)
    wire.add(204)
    resumed = put_image(client, owner, "/api/users/me/avatar", operation)
    assert resumed.status_code == 200 and body(resumed)["avatar"]["id"] == operation
    assert api_client().get(avatar["url"]).status_code == 404


def test_s3_foreign_modification_does_not_call_storage(image_actor: Any, s3: Any) -> None:
    client, owner = image_actor
    _, wire = s3
    record = body(send(client, owner, "POST", "/api/posts", payload()))
    other = api_client()
    other_id = body(signup(other, token(other), "s3_other", "s3-other@example.test"))["id"]
    path = "/api/posts/" + record["id"] + "/image"
    assert put_image(other, other_id, path).status_code == 403
    assert wire.requests == []
    assert api_client().get("/api/media/content/invalid").status_code == 404


def test_s3_orphan_cleanup_uses_listing_and_delete_factory(s3: Any) -> None:
    from media_assets.cleanup import cleanup_images
    from media_assets.models import ImageScan
    _, wire = s3
    wire.add(200, listing(1, 2, False))
    wire.add(204)
    counts = cleanup_images()
    assert counts == {"retired": 0, "deleted": 0, "reconciled": 1, "temporary": 0}
    assert [request.method for request in wire.requests] == ["GET", "DELETE"]
    assert ImageScan.objects.get(name="local").cursor is None


def test_s3_parse_failure_is_503_and_unknown_put_preserves_attachment(
    image_actor: Any, s3: Any, api_log_output: Any,
) -> None:
    client, owner = image_actor
    _, wire = s3
    wire.add(200)
    first = put_image(client, owner, "/api/users/me/avatar")
    avatar = body(first)["avatar"]
    # The HTTP boundary must preserve the storage-specific 503, without raw SDK data.
    wire.add(200, b"abc", {"content-length": "3", "last-modified": "PRIVATE-not-a-date"})
    response = api_client().get(avatar["url"])
    assert response.status_code == 503 and body(response)["code"] == "STORAGE_UNAVAILABLE"
    operation = str(uuid4())
    wire.error(500, "InternalError")
    wire.add(200, b"abc", {"content-length": "3", "last-modified": "PRIVATE-not-a-date"})
    response = put_image(client, owner, "/api/users/me/avatar", operation)
    assert response.status_code == 503 and body(response)["code"] == "STORAGE_UNAVAILABLE"
    assert str(UserAvatar.objects.get(user_id=owner).object_id) == avatar["id"]
    assert ImageObject.objects.get(pk=avatar["id"]).state == "attached"
    pending = ImageObject.objects.get(pk=operation)
    assert pending.state == "pending" and pending.written_at is None
    assert "PRIVATE-not-a-date" not in response.content.decode()
    assert "PRIVATE-not-a-date" not in api_log_output.getvalue()
