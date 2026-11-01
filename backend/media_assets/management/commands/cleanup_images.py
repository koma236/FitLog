from time import perf_counter
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from common.observability import emit_maintenance
from media_assets.cleanup import cleanup_images
from media_assets.models import ImageCleanupJob


class Command(BaseCommand):
    help = "Retire abandoned image operations and reconcile private objects in bounded batches."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args: Any, **options: Any) -> None:
        limit = options["limit"]
        if not 1 <= limit <= 1000:
            raise CommandError("limit must be 1..1000")
        started = perf_counter()
        try:
            result = cleanup_images(limit)
            result["pending_jobs"] = ImageCleanupJob.objects.filter(completed_at__isnull=True).count()
        except Exception:
            emit_maintenance("cleanup_images", max(0, int((perf_counter()-started)*1000)), failed=True)
            raise CommandError("Image cleanup failed; retry the command.") from None
        emit_maintenance("cleanup_images", max(0, int((perf_counter()-started)*1000)), counts=result)
