"""Drop Gunicorn messages/URLs/tracebacks while retaining severity events."""
import logging
import os
import sys

from gunicorn.config import Config
from gunicorn.glogging import Logger

from common.observability import SERVER_EVENTS, SafeFormatter, SafeStreamHandler


class ServerEventFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        event = SERVER_EVENTS.get(record.levelno)
        if event is None:
            return False
        record.__dict__["fitlog_event"] = {"event": event, "request_id": None}
        return True


class SafeGunicornLogger(Logger):
    def setup(self, cfg: Config) -> None:
        handler = SafeStreamHandler(sys.stderr)
        handler.setFormatter(SafeFormatter(
            os.environ.get("FITLOG_LOG_FORMAT", "text"),
            os.environ.get("FITLOG_APP_VERSION", "unknown"),
        ))
        handler.addFilter(ServerEventFilter())
        self.error_log.handlers = [handler]
        self.error_log.setLevel(logging.INFO)
        self.error_log.propagate = False
        self.access_log.handlers = []
        self.access_log.propagate = False
        self.access_log.disabled = True
