"""usernameへのフォールバックを持たないメール認証。"""
from typing import Any

from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import ValidationError
from django.db.models.functions import Lower
from django.http import HttpRequest

from accounts.models import User
from accounts.validation import normalized_email


class EmailBackend(ModelBackend):
    def authenticate(
        self, request: HttpRequest | None, username: str | None = None,
        password: str | None = None, **kwargs: Any,
    ) -> User | None:
        email = kwargs.get("email")
        if not isinstance(email, str) or password is None:
            return None
        try:
            email = normalized_email(email)
        except ValidationError:
            return None
        user = User.objects.alias(email_lower=Lower("email")).filter(email_lower=email).first()
        if user is None:
            User().set_password(password)
            return None
        # inactiveも実password照合を経て、同じ認証失敗へまとめる。
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
