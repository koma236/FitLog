"""Comment identities survive content deletion; counters are derived, never stored."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Length
from django.db.models.lookups import GreaterThanOrEqual, LessThanOrEqual


class CommentIdentity(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    post_uuid = models.UUIDField()


class Comment(models.Model):
    identity = models.OneToOneField(
        CommentIdentity, primary_key=True, on_delete=models.PROTECT, db_column="id"
    )
    post = models.ForeignKey("workouts.Post", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    body = models.TextField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=["post", "created_at", "identity"])]
        constraints = [
            models.CheckConstraint(
                condition=GreaterThanOrEqual(Length("body"), 1)
                & LessThanOrEqual(Length("body"), 500),
                name="social_comment_body_length",
            )
        ]


class Like(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey("workouts.Post", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["post", "user"], name="social_like_post_user")
        ]
