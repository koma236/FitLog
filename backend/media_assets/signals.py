"""Retirement survives target cascades; no storage IO runs inside signals."""

from typing import Any
from uuid import UUID

from django.db import DatabaseError, transaction
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

from common.observability import emit_image_retry
from media_assets.models import ImageCleanupJob, ImageObject, PostImage, UserAvatar


def try_cleanup(identity: UUID) -> None:
    from media_assets.cleanup import clean_one

    try:
        clean_one(identity)
    except DatabaseError:
        emit_image_retry()


def retire(image: ImageObject) -> None:
    image.state = "retired"
    image.retired_at = timezone.now()
    image.save(update_fields=["state", "retired_at"])
    ImageCleanupJob.objects.get_or_create(object=image)
    transaction.on_commit(lambda: try_cleanup(image.pk))


@receiver(pre_delete, sender=PostImage)
@receiver(pre_delete, sender=UserAvatar)
def retire_attachment(
    sender: type[PostImage] | type[UserAvatar], instance: PostImage | UserAvatar, **kwargs: Any
) -> None:
    with transaction.atomic():
        image = ImageObject.objects.select_for_update().get(pk=instance.object_id)
        retire(image)
