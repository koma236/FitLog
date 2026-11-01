"""FL08-AC3: command outcomes, expiry fixtures and retry state, not deletion internals."""
import json
import logging
import traceback
from datetime import timedelta
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, transaction
from django.utils import timezone

from common.observability import SafeFormatter, SafeStreamHandler
from media_assets.exceptions import ImageError
from media_assets.models import ImageCleanupJob, ImageObject

pytestmark = pytest.mark.django_db(transaction=True)
SECRET = "postgresql://private-user:private-password@private-host/private-db"


@pytest.fixture
def operations_output(monkeypatch: pytest.MonkeyPatch, settings: Any,
                      tmp_path: Path) -> StringIO:
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    output = StringIO()
    sinks = {id(h): h for name in ("", "fitlog.api", "fitlog.maintenance")
             for h in logging.getLogger(name).handlers if isinstance(h, SafeStreamHandler)}
    assert sinks
    for h in sinks.values():
        monkeypatch.setattr(h, "stream", output)
        monkeypatch.setattr(h, "formatter", SafeFormatter(mode="json"))
    return output


def events(output: StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in output.getvalue().splitlines()]


def image(state: str = "retired") -> ImageObject:
    identity = uuid4()
    return ImageObject.objects.create(
        id=identity, target_kind="post", target_uuid=uuid4(), actor=uuid4(), key=identity.hex + ".png",
        digest="a" * 64, size=1, content_type="image/png", width=1, height=1, state=state,
    )


def test_auth_cleanup_preserves_live_data_and_emits_one_summary(operations_output: StringIO) -> None:
    from django.contrib.sessions.models import Session

    from accounts.models import AuthRateLimit
    now = timezone.now().replace(second=0, microsecond=0)
    for age in [0, 1, 2]:
        AuthRateLimit.objects.create(ip_digest="a" * 64, window_start=now-timedelta(minutes=age), count=1)
    Session.objects.create(session_key="live", session_data="private-live-marker", expire_date=now+timedelta(days=1))
    Session.objects.create(session_key="expired", session_data="private-expired-marker", expire_date=now-timedelta(days=1))
    stdout = StringIO()
    with patch("django.utils.timezone.now", return_value=now):
        call_command("cleanup_auth_security", stdout=stdout)
    assert stdout.getvalue() == ""
    assert list(Session.objects.values_list("session_key", flat=True)) == ["live"]
    assert set(AuthRateLimit.objects.values_list("window_start", flat=True)) == {now, now-timedelta(minutes=1)}
    rows = events(operations_output)
    assert len(rows) == 1 and rows[0]["event"] == "maintenance_complete"
    assert rows[0]["command"] == "cleanup_auth_security" and rows[0]["level"] == "INFO"
    assert "counts" not in rows[0] and rows[0]["request_id"] is None
    call_command("cleanup_auth_security", stdout=stdout)
    assert Session.objects.filter(session_key="live").exists()
    assert "private-live-marker" not in operations_output.getvalue()


def test_images_cleanup_reports_counts_and_is_idempotent(operations_output: StringIO) -> None:
    retired = image()
    active = image("attached")
    ImageCleanupJob.objects.create(object=retired)
    call_command("cleanup_images", stdout=StringIO())
    row = events(operations_output)[-1]
    assert row["event"] == "maintenance_complete"
    assert row["counts"] == {"retired": 0, "deleted": 1, "reconciled": 0, "temporary": 0, "pending_jobs": 0}
    assert ImageObject.objects.get(pk=active.pk).state == "attached"
    call_command("cleanup_images", stdout=StringIO())
    assert events(operations_output)[-1]["counts"]["deleted"] == 0
    assert str(retired.pk) not in operations_output.getvalue()


def test_clean_one_failure_is_deferred_not_a_failed_batch(operations_output: StringIO) -> None:
    retired = image()
    job = ImageCleanupJob.objects.create(object=retired)
    with patch("media_assets.storage.LocalStorage.delete", side_effect=ImageError(503, SECRET)):
        call_command("cleanup_images", stdout=StringIO())
    job.refresh_from_db()
    assert job.completed_at is None and job.attempts == 1
    assert job.next_attempt_at > timezone.now()
    row = events(operations_output)[-1]
    assert row["event"] == "maintenance_complete"
    assert row["counts"]["pending_jobs"] == 1 and row["counts"]["deleted"] == 0
    assert SECRET not in operations_output.getvalue()


@pytest.mark.parametrize("target", [
    "media_assets.storage.LocalStorage.list_page",
    "media_assets.storage.LocalStorage.sweep_temporary",
])
def test_propagated_storage_failures_are_fixed_non_success(target: str,
                                                          operations_output: StringIO) -> None:
    with patch(target, side_effect=ImageError(503, SECRET)):
        with pytest.raises(CommandError) as caught:
            call_command("cleanup_images", stdout=StringIO())
    assert SECRET not in "".join(traceback.format_exception(caught.value))
    row = events(operations_output)[-1]
    assert row["event"] == "maintenance_failed" and row["level"] == "ERROR"
    assert "counts" not in row and SECRET not in operations_output.getvalue()


def test_reconcile_delete_failure_is_not_clean_one_deferral(operations_output: StringIO) -> None:
    from media_assets.storage import StoredObject
    orphan = StoredObject("b" * 32 + ".png", timezone.now()-timedelta(hours=2))
    with patch("media_assets.storage.LocalStorage.list_page", return_value=([orphan], None)), patch(
        "media_assets.storage.LocalStorage.delete", side_effect=ImageError(503, SECRET),
    ):
        with pytest.raises(CommandError):
            call_command("cleanup_images", stdout=StringIO())
    assert events(operations_output)[-1]["event"] == "maintenance_failed"
    assert SECRET not in operations_output.getvalue()


@pytest.mark.parametrize("command", ["cleanup_images", "cleanup_auth_security"])
@pytest.mark.parametrize("error", [DatabaseError(SECRET), RuntimeError(SECRET)])
def test_command_errors_suppress_original_chain(command: str, error: Exception,
                                                operations_output: StringIO) -> None:
    target = ("media_assets.management.commands.cleanup_images.cleanup_images" if command == "cleanup_images"
              else "accounts.management.commands.cleanup_auth_security.call_command")
    with patch(target, side_effect=error):
        with pytest.raises(CommandError) as caught:
            call_command(command, stdout=StringIO())
    assert SECRET not in "".join(traceback.format_exception(caught.value))
    row = events(operations_output)[-1]
    assert row["event"] == "maintenance_failed" and row["command"] == command


def test_final_count_failure_is_failed_even_if_cleanup_ran(operations_output: StringIO) -> None:
    with patch("media_assets.management.commands.cleanup_images.cleanup_images", return_value={
        "retired": 0, "deleted": 0, "reconciled": 0, "temporary": 0,
    }), patch("media_assets.models.ImageCleanupJob.objects.filter", side_effect=DatabaseError(SECRET)):
        with pytest.raises(CommandError):
            call_command("cleanup_images", stdout=StringIO())
    assert events(operations_output)[-1]["event"] == "maintenance_failed"


@pytest.mark.parametrize("limit", [0, 1001])
def test_range_rejection_has_no_maintenance_event(limit: int, operations_output: StringIO) -> None:
    with pytest.raises(CommandError, match="limit must be 1..1000"):
        call_command("cleanup_images", limit=limit)
    assert events(operations_output) == []


def test_cli_boundary_nonzero_and_fixed_error_stream(operations_output: StringIO) -> None:
    from media_assets.management.commands.cleanup_images import Command
    stdout, stderr = StringIO(), StringIO()
    with patch("media_assets.management.commands.cleanup_images.cleanup_images",
               side_effect=ImageError(503, SECRET)):
        with pytest.raises(SystemExit) as caught:
            Command(stdout=stdout, stderr=stderr).run_from_argv(["manage.py", "cleanup_images"])
    assert caught.value.code == 1
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "CommandError: Image cleanup failed; retry the command.\n"
    assert events(operations_output)[-1]["event"] == "maintenance_failed"
    assert SECRET not in stderr.getvalue()+operations_output.getvalue()


def test_on_commit_retry_is_observed_without_object_id(operations_output: StringIO) -> None:
    from media_assets.signals import retire
    obj = image("attached")
    with patch("media_assets.cleanup.clean_one", side_effect=DatabaseError(SECRET)):
        with transaction.atomic():
            retire(obj)
    rows = events(operations_output)
    assert len(rows) == 1 and rows[0]["event"] == "image_cleanup_retry"
    assert rows[0]["command"] is None and rows[0]["request_id"] is None
    assert str(obj.pk) not in operations_output.getvalue() and SECRET not in operations_output.getvalue()


@pytest.mark.parametrize("limit", [1, 1000])
def test_limit_boundaries_are_valid(limit: int, operations_output: StringIO) -> None:
    call_command("cleanup_images", limit=limit, stdout=StringIO())
    assert events(operations_output)[-1]["event"] == "maintenance_complete"


def test_cli_traceback_conversion_has_no_original_exception(operations_output: StringIO) -> None:
    from media_assets.management.commands.cleanup_images import Command
    with patch("media_assets.management.commands.cleanup_images.cleanup_images",
               side_effect=DatabaseError(SECRET)):
        with pytest.raises(CommandError) as caught:
            Command(stdout=StringIO(), stderr=StringIO()).run_from_argv(
                ["manage.py", "cleanup_images", "--traceback"],
            )
    assert SECRET not in "".join(traceback.format_exception(caught.value))
    assert events(operations_output)[-1]["event"] == "maintenance_failed"


def test_parse_rejection_is_nonzero_without_a_maintenance_event(operations_output: StringIO) -> None:
    from media_assets.management.commands.cleanup_images import Command
    with pytest.raises(SystemExit) as caught:
        Command(stdout=StringIO(), stderr=StringIO()).run_from_argv(
            ["manage.py", "cleanup_images", "--limit", "not-a-number"],
        )
    assert caught.value.code == 2
    assert events(operations_output) == []
