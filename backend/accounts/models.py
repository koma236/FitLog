"""将来の認証に先立ち、初回migrationからUUID主キーを使用する。"""
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
