"""既存ID/password/emailを保持し、検査後に認証用の制約を追加する。"""
import re

import django.db.models.functions.text
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

import accounts.models


def migrate_accounts(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    user_model = apps.get_model("accounts", "User")
    rows = list(user_model.objects.using(schema_editor.connection.alias).all())
    usernames: dict[str, list[str]] = {}
    emails: dict[str, list[str]] = {}
    violations: set[str] = set()
    for user in rows:
        identifier = str(user.pk)
        if not re.fullmatch(r"[a-z0-9_]{3,30}", user.username) or user.username in {"me", "search"}:
            violations.add(f"{identifier}:invalid_username")
        usernames.setdefault(user.username.lower(), []).append(identifier)
        if user.email:
            emails.setdefault(user.email.lower(), []).append(identifier)
            if not user.email.isascii() or user.email != user.email.strip():
                violations.add(f"{identifier}:unsupported_legacy_email")
    for kind, groups in (("duplicate_username", usernames), ("duplicate_email", emails)):
        for identifiers in groups.values():
            if len(identifiers) > 1:
                violations.update(f"{identifier}:{kind}" for identifier in identifiers)
    if violations:
        raise RuntimeError("Account migration stopped: " + ", ".join(sorted(violations)))
    for user in rows:
        user.display_name = user.username
        user.save(using=schema_editor.connection.alias, update_fields=["display_name"])


class Migration(migrations.Migration):
    atomic = True
    dependencies = [("accounts", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="user", name="display_name",
            field=models.CharField(default="", max_length=50), preserve_default=False,
        ),
        migrations.RunPython(migrate_accounts, migrations.RunPython.noop),
        migrations.AlterModelManagers(name="user", managers=[("objects", accounts.models.UserManager())]),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("username"),
                name="fitlog_user_username_ci_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("email"), condition=~models.Q(email=""),
                name="fitlog_user_email_ci_unique",
            ),
        ),
        migrations.CreateModel(
            name="AuthRateLimit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ip_digest", models.CharField(max_length=64)),
                ("window_start", models.DateTimeField(db_index=True)),
                ("count", models.PositiveIntegerField()),
            ],
            options={"constraints": [models.UniqueConstraint(
                fields=("ip_digest", "window_start"), name="fitlog_auth_rate_window_unique",
            )]},
        ),
    ]
