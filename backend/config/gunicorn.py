"""No request data or proxy trust is inferred by the WSGI server."""
bind = "0.0.0.0:8000"
workers = 2
worker_class = "sync"
timeout = 60
graceful_timeout = 30
preload_app = False
forwarded_allow_ips = ""
secure_scheme_headers: dict[str, str] = {}
accesslog = None
errorlog = "-"
loglevel = "info"
logger_class = "common.gunicorn_logging.SafeGunicornLogger"
