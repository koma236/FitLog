"""入力の機密値をエラーへ含めないアカウント作成境界。"""
from django.db import IntegrityError, connection, transaction
from django.db.models.functions import Lower

from accounts.models import User


class DuplicateAccount(Exception):
    def __init__(self, field: str) -> None:
        self.field = field


def duplicate_field(username: str, email: str) -> str | None:
    if User.objects.alias(value=Lower("username")).filter(value=username).exists():
        return "username"
    if User.objects.alias(value=Lower("email")).filter(value=email).exists():
        return "email"
    return None


def create_account(username: str, email: str, password: str, display_name: str) -> User:
    # 検証とhashの間、Userの保存中のどちらにもcounterの行ロックはない。
    user = User.objects.prepare_user(username, email, password, display_name=display_name)
    duplicate = duplicate_field(user.username, user.email)
    if duplicate:
        raise DuplicateAccount(duplicate)
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, User._meta.db_table)
    username_unique = {
        name for name, info in constraints.items()
        if info["unique"] and info["columns"] == ["username"]
    }
    known = username_unique | {"fitlog_user_username_ci_unique", "fitlog_user_email_ci_unique"}
    try:
        with transaction.atomic():
            user.save(force_insert=True)
    except IntegrityError as exc:
        diagnostic = getattr(exc.__cause__, "diag", None)
        name = getattr(diagnostic, "constraint_name", None)
        if name not in known:
            raise
        duplicate = duplicate_field(user.username, user.email)
        if duplicate is None:
            duplicate = "email" if name == "fitlog_user_email_ci_unique" else "username"
        raise DuplicateAccount(duplicate) from None
    return user
