"""A persistent identity prevents deleted record URLs being reused."""

import uuid

from django.conf import settings
from django.db import models


class PostIdentity(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)


class Post(models.Model):
    identity = models.OneToOneField(
        PostIdentity, primary_key=True, on_delete=models.PROTECT, db_column="id"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    performed_on = models.DateField()
    note = models.TextField(blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    minutes = models.PositiveSmallIntegerField(null=True)
    kind = models.CharField(max_length=8, null=True)
    minutes_public = models.BooleanField(default=False)
    kind_public = models.BooleanField(default=False)
    energy_kcal = models.PositiveIntegerField(null=True)
    energy_method = models.CharField(max_length=20, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-created_at", "-identity"]),
            models.Index(fields=["-created_at", "-identity"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(minutes__isnull=True)
                | models.Q(minutes__gte=1, minutes__lte=240),
                name="workout_minutes_range",
            ),
            models.CheckConstraint(
                condition=models.Q(kind__isnull=True)
                | models.Q(kind__in=["general", "squat", "vigorous"]),
                name="workout_kind_choice",
            ),
        ]


class WorkoutExercise(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="exercises")
    name = models.CharField(max_length=80)
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["post", "position"], name="workout_exercise_position")
        ]


class WorkoutSet(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exercise = models.ForeignKey(WorkoutExercise, on_delete=models.CASCADE, related_name="sets")
    position = models.PositiveSmallIntegerField()
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2)
    reps = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["exercise", "position"], name="workout_set_position"),
            models.CheckConstraint(
                condition=models.Q(weight_kg__gte=0, weight_kg__lte=999.99),
                name="workout_weight_range",
            ),
            models.CheckConstraint(
                condition=models.Q(reps__gte=1, reps__lte=999), name="workout_reps_range"
            ),
        ]
