"""失効済みセッションと2分以上前の試行窓を清掃する。"""
from datetime import timedelta
from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import AuthRateLimit


class Command(BaseCommand):
    help = "Remove expired database sessions and old authentication rate windows"

    def handle(self, *args: Any, **options: Any) -> None:
        call_command("clearsessions", verbosity=0)
        now = timezone.now()
        current_window = now.replace(second=0, microsecond=0)
        AuthRateLimit.objects.filter(window_start__lte=current_window - timedelta(minutes=2)).delete()
        self.stdout.write("Authentication security cleanup completed")
