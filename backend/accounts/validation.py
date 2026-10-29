"""登録APIとUserManagerで共有する、新規アカウントの入力規則。"""
import re
import unicodedata
from typing import TYPE_CHECKING

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

if TYPE_CHECKING:
    from accounts.models import User

USERNAME_PATTERN = r"[a-z0-9_]{3,30}"


def normalized_email(value: str) -> str:
    email = value.strip().lower()
    if not email or len(email) > 254 or not email.isascii():
        raise ValidationError("メールアドレスを確認してください。")
    validate_email(email)
    return email


def normalized_display_name(value: str) -> str:
    name = value.strip()
    if not 1 <= len(name) <= 50 or any(unicodedata.category(char) == "Cc" for char in name):
        raise ValidationError("表示名は制御文字を含まない1〜50文字にしてください。")
    return name


def validate_new_user(user: "User", password: str | None) -> None:
    """値は応答に埋め込まず、各フィールドに固定の案内を返す。"""
    errors: dict[str, list[str]] = {}
    user.username = user.username.strip().lower()
    user.display_name = user.display_name.strip()
    if not re.fullmatch(USERNAME_PATTERN, user.username) or user.username in {"me", "search"}:
        errors["username"] = ["ユーザー名は小文字の英数字と_で3〜30文字にしてください。"]
    try:
        user.email = normalized_email(user.email)
    except ValidationError:
        errors["email"] = ["有効なメールアドレスを入力してください。"]
    try:
        user.display_name = normalized_display_name(user.display_name)
    except ValidationError:
        errors["display_name"] = ["表示名は制御文字を含まない1〜50文字にしてください。"]
    if password is None or not 12 <= len(password) <= 128:
        errors["password"] = ["パスワードは12〜128文字にしてください。"]
    else:
        try:
            validate_password(password, user)
        except ValidationError:
            errors["password"] = ["推測されにくい、他の登録情報と異なるパスワードを入力してください。"]
    if errors:
        raise ValidationError(errors)
