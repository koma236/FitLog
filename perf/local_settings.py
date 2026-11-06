"""Existing local settings plus a fail-closed guard for the owned perf DB."""
import os

from config import settings as base
from perf.seed import guard

guard(os.environ["PERF_RUN_ID"], base.DATABASES["default"])
globals().update({key: getattr(base, key) for key in dir(base) if key.isupper()})
