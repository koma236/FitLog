from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from media_assets.cleanup import cleanup_images
from media_assets.exceptions import ImageError


class Command(BaseCommand):
    help = "Retire abandoned image operations and reconcile private objects in bounded batches."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args: Any, **options: Any) -> None:
        limit = options["limit"]
        if not 1 <= limit <= 1000:
            raise CommandError("limit must be 1..1000")
        try:
            result = cleanup_images(limit)
        except ImageError:
            raise CommandError("Private storage unavailable; retry cleanup later.") from None
        self.stdout.write(str(result))
