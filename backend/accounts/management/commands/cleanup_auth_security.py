"""失効済みセッションと2分以上前の試行窓を清掃する。"""
from datetime import timedelta
from time import perf_counter
from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import AuthRateLimit
from common.observability import emit_maintenance


class Command(BaseCommand):
    help = "Remove expired database sessions and old authentication rate windows"

    def handle(self, *args: Any, **options: Any) -> None:
        started = perf_counter()
        try:
            call_command("clearsessions", verbosity=0)
            now = timezone.now()
            current_window = now.replace(second=0, microsecond=0)
            AuthRateLimit.objects.filter(window_start__lte=current_window - timedelta(minutes=2)).delete()
        except Exception:
            emit_maintenance("cleanup_auth_security", max(0, int((perf_counter()-started)*1000)), failed=True)
            raise CommandError("Authentication cleanup failed; retry the command.") from None
        emit_maintenance("cleanup_auth_security", max(0, int((perf_counter()-started)*1000)))
