"""The signed payload contains an opaque asset ID only, never a storage path."""

import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from django.core import signing

from accounts.models import User
from media_assets.models import ImageObject, PostImage, UserAvatar
from workouts.models import Post

SALT = "fitlog.image.content.v1"


def image_dto(image: ImageObject | None) -> dict[str, Any] | None:
    if image is None or image.state != "attached":
        return None
    issued = int(time.time())
    token = signing.dumps({"id": str(image.pk), "at": issued}, salt=SALT)
    return {
        "id": str(image.pk),
        "url": "/api/media/content/" + token,
        "expires_at": datetime.fromtimestamp(issued + 300, UTC).isoformat().replace("+00:00", "Z"),
        "width": image.width,
        "height": image.height,
        "content_type": image.content_type,
    }


def resolve_token(token: str) -> UUID:
    if len(token) > 512:
        raise signing.BadSignature("Invalid image token")
    value = signing.loads(token, salt=SALT, max_age=300)
    if (
        not isinstance(value, dict)
        or set(value) != {"id", "at"}
        or type(value["at"]) is not int
        or not 0 <= time.time() - value["at"] <= 300
    ):
        raise signing.BadSignature("Invalid image token")
    try:
        identity = UUID(value["id"])
        if str(identity) != value["id"]:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise signing.BadSignature("Invalid image token") from None
    return identity


def post_image(post: Post) -> dict[str, Any] | None:
    try:
        return image_dto(post.image_attachment.object)
    except PostImage.DoesNotExist:
        return None


def avatar(user: User) -> dict[str, Any] | None:
    try:
        return image_dto(user.avatar_attachment.object)
    except UserAvatar.DoesNotExist:
        return None
