"""Immutable operation identities; attachment and retirement are transactional."""

from django.db import models
from django.utils import timezone


class ImageObject(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    target_kind = models.CharField(max_length=6)
    target_uuid = models.UUIDField()
    actor = models.UUIDField()
    backend = models.CharField(max_length=16, default="local")
    key = models.CharField(max_length=36, unique=True)
    digest = models.CharField(max_length=64)
    size = models.PositiveIntegerField()
    content_type = models.CharField(max_length=10)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    state = models.CharField(max_length=8, default="pending", db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    written_at = models.DateTimeField(null=True)
    retired_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(state__in=["pending", "attached", "retired"]),
                name="image_state_choice",
            ),
            models.CheckConstraint(
                condition=models.Q(target_kind__in=["post", "avatar"]), name="image_target_choice"
            ),
            models.CheckConstraint(
                condition=models.Q(backend="local"), name="image_backend_choice"
            ),
            models.CheckConstraint(
                condition=models.Q(content_type__in=["image/jpeg", "image/png"]),
                name="image_type_choice",
            ),
            models.CheckConstraint(
                condition=models.Q(size__gte=1, size__lte=5242880), name="image_size_range"
            ),
            models.CheckConstraint(
                condition=models.Q(width__gte=1, height__gte=1), name="image_dimensions_positive"
            ),
        ]


class PostImage(models.Model):
    post = models.OneToOneField(
        "workouts.Post", on_delete=models.CASCADE, related_name="image_attachment"
    )
    object = models.OneToOneField(ImageObject, on_delete=models.PROTECT)


class UserAvatar(models.Model):
    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="avatar_attachment"
    )
    object = models.OneToOneField(ImageObject, on_delete=models.PROTECT)


class ImageCleanupJob(models.Model):
    object = models.OneToOneField(ImageObject, on_delete=models.PROTECT, related_name="cleanup_job")
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    completed_at = models.DateTimeField(null=True)


class ImageScan(models.Model):
    name = models.CharField(max_length=16, primary_key=True)
    cursor = models.CharField(max_length=36, null=True)
