"""UUIDを保持したアカウントと認証試行の固定窓。"""
import uuid
from typing import Any, ClassVar

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models
from django.db.models.functions import Lower

from accounts.validation import validate_new_user


class UserManager(DjangoUserManager["User"]):
    use_in_migrations = True

    def prepare_user(
        self, username: str, email: str | None, password: str | None, **extra_fields: Any,
    ) -> "User":
        user = self.model(username=username, email=email or "", **extra_fields)
        validate_new_user(user, password)
        user.set_password(password)
        return user

    def create_user(
        self, username: str, email: str | None = None, password: str | None = None,
        **extra_fields: Any,
    ) -> "User":
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        user = self.prepare_user(username, email, password, **extra_fields)
        user.save(using=self._db)
        return user

    def create_superuser(
        self, username: str, email: str | None = None, password: str | None = None,
        **extra_fields: Any,
    ) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields["is_staff"] is not True or extra_fields["is_superuser"] is not True:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True")
        return self.create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_name = models.CharField(max_length=50)
    bio = models.CharField(max_length=160, blank=True, default="")
    objects: ClassVar[UserManager] = UserManager()
    REQUIRED_FIELDS = ["email", "display_name"]

    class Meta:
        abstract = False
        verbose_name = "user"
        verbose_name_plural = "users"
        constraints = [
            models.UniqueConstraint(Lower("username"), name="fitlog_user_username_ci_unique"),
            models.UniqueConstraint(
                Lower("email"), condition=~models.Q(email=""),
                name="fitlog_user_email_ci_unique",
            ),
        ]


class AuthRateLimit(models.Model):
    ip_digest = models.CharField(max_length=64)
    window_start = models.DateTimeField(db_index=True)
    count = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["ip_digest", "window_start"], name="fitlog_auth_rate_window_unique",
            ),
        ]


class ProfileHealth(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile_health")
    height_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    age = models.PositiveSmallIntegerField(null=True, blank=True)
    formula = models.CharField(max_length=6, null=True, blank=True)
    activity = models.CharField(max_length=6, null=True, blank=True)
    height_public = models.BooleanField(default=False)
    weight_public = models.BooleanField(default=False)
    age_public = models.BooleanField(default=False)
    formula_public = models.BooleanField(default=False)
    activity_public = models.BooleanField(default=False)
    bmr_public = models.BooleanField(default=False)
    tdee_public = models.BooleanField(default=False)
    intake_public = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(height_cm__isnull=True) | models.Q(height_cm__gte=100, height_cm__lte=250), name="profile_height_range"),
            models.CheckConstraint(condition=models.Q(weight_kg__isnull=True) | models.Q(weight_kg__gte=20, weight_kg__lte=350), name="profile_weight_range"),
            models.CheckConstraint(condition=models.Q(age__isnull=True) | models.Q(age__gte=0, age__lte=120), name="profile_age_range"),
            models.CheckConstraint(condition=models.Q(formula__isnull=True) | models.Q(formula__in=["male", "female"]), name="profile_formula_choice"),
            models.CheckConstraint(condition=models.Q(activity__isnull=True) | models.Q(activity__in=["low", "medium", "high"]), name="profile_activity_choice"),
        ]
