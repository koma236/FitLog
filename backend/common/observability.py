"""Allowlisted event fields only; never render arbitrary messages or tracebacks."""
import json
import logging
import math
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from django.http import HttpRequest

METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
COMMANDS = frozenset({"cleanup_auth_security", "cleanup_images"})
COUNT_KEYS = ("retired", "deleted", "reconciled", "temporary", "pending_jobs")
SERVER_EVENTS = {
    logging.INFO: "server_info", logging.WARNING: "server_warning",
    logging.ERROR: "server_error", logging.CRITICAL: "server_critical",
}
COMMON = {"event", "request_id"}
API = COMMON | {"method", "route_template", "status", "duration_ms"}
MAINTENANCE = COMMON | {"command", "duration_ms"}


def _integer(value: object) -> bool:
    return type(value) is int and 0 <= value <= 2**63 - 1


def _uuid(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def _allowed(record: logging.LogRecord) -> dict[str, Any] | None:
    fields = getattr(record, "fitlog_event", None)
    if type(fields) is not dict:
        return None
    event = fields.get("event")
    if type(event) is not str:
        return None
    if record.name == "fitlog.api" and event in {"api_request", "api_error"}:
        status = fields.get("status")
        if set(fields) != API or type(status) is not int or not 100 <= status <= 599:
            return None
        level = logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO
        if record.levelno != level or event != ("api_error" if status >= 400 else "api_request"):
            return None
        method = fields["method"]
        route = fields["route_template"]
        if (not _uuid(fields["request_id"]) or type(method) is not str
                or method not in METHODS | {"OTHER"} or type(route) is not str
                or not re.fullmatch(r"[A-Za-z0-9_/:<>.\-]{1,256}", route)
                or not _integer(fields["duration_ms"])):
            return None
    elif record.name == "fitlog.maintenance" and event in {"maintenance_complete", "maintenance_failed"}:
        has_counts = event == "maintenance_complete" and fields.get("command") == "cleanup_images"
        if (set(fields) != MAINTENANCE | ({"counts"} if has_counts else set())
                or fields["request_id"] is not None or type(fields["command"]) is not str
                or fields["command"] not in COMMANDS
                or not _integer(fields["duration_ms"])
                or record.levelno != (logging.ERROR if event == "maintenance_failed" else logging.INFO)):
            return None
        if has_counts:
            counts = fields["counts"]
            if type(counts) is not dict or set(counts) != set(COUNT_KEYS) or not all(
                _integer(v) for v in counts.values()
            ):
                return None
            fields = {**fields, "counts": {k: counts[k] for k in COUNT_KEYS}}
    elif record.name == "fitlog.maintenance" and event == "image_cleanup_retry":
        if (set(fields) != MAINTENANCE or fields["request_id"] is not None
                or fields["command"] is not None or fields["duration_ms"] is not None
                or record.levelno != logging.WARNING):
            return None
    elif record.name == "gunicorn.error" and event in SERVER_EVENTS.values():
        if (set(fields) != COMMON or fields["request_id"] is not None
                or SERVER_EVENTS.get(record.levelno) != event):
            return None
    else:
        return None
    return fields


class SafeFormatter(logging.Formatter):
    def __init__(self, mode: str = "text", app_version: str = "unknown") -> None:
        super().__init__()
        if mode not in {"text", "json"}:
            raise ValueError("Invalid FitLog log format")
        self.mode = mode
        self.app_version = (app_version if type(app_version) is str
                            and re.fullmatch(r"[a-f0-9]{7,40}", app_version) else "unknown")

    def format(self, record: logging.LogRecord) -> str:
        created = record.created
        try:
            if type(created) not in {int, float} or not math.isfinite(created):
                raise ValueError
            timestamp = datetime.fromtimestamp(created, UTC)
        except (ValueError, OverflowError, OSError):
            timestamp = datetime.now(UTC)
        fields = _allowed(record)
        level = logging.getLevelName(record.levelno) if fields is not None else "WARNING"
        if fields is None:
            fields = {"event": "log_record_discarded", "request_id": None}
        obj = {"timestamp": timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
               "level": level, **fields, "app_version": self.app_version}
        if self.mode == "json":
            return json.dumps(obj, ensure_ascii=True, separators=(",", ":"))
        pieces = [str(obj["level"]), str(obj["event"])]
        for key in ("status", "request_id", "command", "method", "route_template", "duration_ms",
                    "app_version", "timestamp", "counts"):
            if key in obj:
                value = obj[key]
                rendered = (json.dumps(value, separators=(",", ":"))
                            if value is None or type(value) is dict else str(value))
                pieces.append(key + "=" + rendered)
        return " ".join(pieces)


class SafeStreamHandler(logging.StreamHandler[Any]):
    def handleError(self, record: logging.LogRecord) -> None:
        # A broken log pipe must not fall back to raw Message/Arguments on stderr.
        return


def emit_api_result(request: HttpRequest, status: int, duration_ms: int) -> None:
    from common.errors import not_found

    match = request.resolver_match
    route = "unmatched" if match is None or match.func is not_found else match.route
    level = logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO
    fields = {"event": "api_error" if status >= 400 else "api_request",
              "request_id": request.META.get("FITLOG_REQUEST_ID"),
              "method": request.method if request.method in METHODS else "OTHER",
              "route_template": route, "status": status, "duration_ms": duration_ms}
    logging.getLogger("fitlog.api").log(level, "", extra={"fitlog_event": fields})


def emit_maintenance(command: str, duration_ms: int, *, failed: bool = False,
                     counts: dict[str, int] | None = None) -> None:
    fields: dict[str, object] = {"event": "maintenance_failed" if failed else "maintenance_complete",
                                "request_id": None, "command": command, "duration_ms": duration_ms}
    if counts is not None:
        fields["counts"] = counts
    logging.getLogger("fitlog.maintenance").log(
        logging.ERROR if failed else logging.INFO, "", extra={"fitlog_event": fields},
    )


def emit_image_retry() -> None:
    logging.getLogger("fitlog.maintenance").warning("", extra={"fitlog_event": {
        "event": "image_cleanup_retry", "request_id": None, "command": None, "duration_ms": None,
    }})
