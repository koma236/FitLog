"""Finite idempotent cleanup; completed jobs do not suppress later orphan scans."""

from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from media_assets.exceptions import ImageError
from media_assets.models import ImageCleanupJob, ImageObject, ImageScan
from media_assets.signals import retire
from media_assets.storage import LocalStorage


def clean_one(identity: UUID) -> bool:
    with transaction.atomic():
        image = ImageObject.objects.select_for_update().get(pk=identity)
        if image.state != "retired":
            return False
        job, _ = ImageCleanupJob.objects.get_or_create(object=image)
        if job.completed_at is not None or job.next_attempt_at > timezone.now():
            return False
        try:
            LocalStorage().delete(image.key)
        except ImageError:
            job.attempts += 1
            job.next_attempt_at = timezone.now() + timedelta(
                seconds=min(3600, 2 ** min(job.attempts, 11))
            )
            job.save(update_fields=["attempts", "next_attempt_at"])
            return False
        job.completed_at = timezone.now()
        job.save(update_fields=["completed_at"])
        return True


def cleanup_images(limit: int = 100) -> dict[str, int]:
    now = timezone.now()
    before = now - timedelta(hours=1)
    counts = {"retired": 0, "deleted": 0, "reconciled": 0}
    pending = list(
        ImageObject.objects.filter(state="pending", created_at__lte=before)
        .order_by("created_at")
        .values_list("pk", flat=True)[:limit]
    )
    for identity in pending:
        with transaction.atomic():
            image = ImageObject.objects.select_for_update().get(pk=identity)
            if image.state == "pending" and image.created_at <= before:
                retire(image)
                counts["retired"] += 1
    jobs = list(
        ImageCleanupJob.objects.filter(completed_at__isnull=True, next_attempt_at__lte=now)
        .order_by("next_attempt_at")
        .values_list("object_id", flat=True)[:limit]
    )
    for identity in jobs:
        counts["deleted"] += int(clean_one(identity))
    # Read the checkpoint briefly; never retain page-wide object locks across I/O.
    with transaction.atomic():
        ImageScan.objects.get_or_create(name="local")
        scan = ImageScan.objects.select_for_update().get(name="local")
        cursor = scan.cursor
    storage = LocalStorage()
    rows, next_cursor = storage.list_page(cursor, limit)
    for stored in rows:
        if stored.modified_at > before:
            continue
        candidate = ImageObject.objects.filter(key=stored.key).first()
        if candidate is not None and candidate.state != "retired":
            continue
        with transaction.atomic():
            found = ImageObject.objects.select_for_update().filter(key=stored.key).first()
            if found is not None and found.state != "retired":
                continue
            # Reserved DB rows always precede file writes, so an unknown aged key cannot be adopted.
            storage.delete(stored.key)
            counts["reconciled"] += 1
    with transaction.atomic():
        scan = ImageScan.objects.select_for_update().get(name="local")
        if scan.cursor == cursor:
            scan.cursor = next_cursor
            scan.save(update_fields=["cursor"])
    counts["temporary"] = storage.sweep_temporary(before)
    return counts
