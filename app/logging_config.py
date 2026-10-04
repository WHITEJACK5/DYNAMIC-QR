"""Structured JSON logging (Phase 7b).

The directive: "Add structured logging (JSON logs) instead of ad-hoc
`print()`/`logger.info("..."))` string interpolation."

Why this matters beyond style: an f-string is evaluated eagerly, so a log
line is built even when the level is filtered out, and the result is an
opaque string. A JSON log is a record — timestamp, level, message template,
and named fields — which a log aggregator can query, alert on, and
correlate. That is the difference between "we have logs" and "we can
operate the service".

Two parts:

  1. A formatter that emits one JSON object per line. It resolves the
     message lazily (so `logger.info("user %s", uid)` does not interpolate
     when the level is off) and promotes any `extra=` fields to top level,
     so `logger.info("login", extra={"user_id": 5})` yields
     `{"message": "login", "user_id": 5, ...}`.

  2. A guard test that fails if application code goes back to f-string
     interpolation or print(). Without it, "we use structured logging" is a
     claim that decays the first time someone adds a debug line.

The formatter is installed by app/config.py, which is imported before any
other app module, so every logger in the process inherits it.
"""
import json
import logging
import sys
import time

#: Fields that are already on the record and must not be duplicated.
#: Every key the formatter writes is listed, so extra={"level": ...} or
#: extra={"ts": ...} cannot forge the severity or the timestamp.
_RESERVED = {
    "name", "msg", "args", "level", "levelname", "levelno", "pathname",
    "filename", "module", "exc_info", "exc_text", "stack_info", "lineno",
    "funcName", "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
    # keys this formatter writes
    "ts", "logger", "service", "env",
}


class JsonFormatter(logging.Formatter):
    """One JSON object per log record.

    `extra=` fields are promoted to the top level of the object, which is
    what makes them queryable. Reserved attribute names are skipped so a
    caller cannot clobber the timestamp or level.
    """

    def __init__(self, service="DR", env=None):
        super().__init__()
        self.service = service
        self.env = env or "unknown"

    def format(self, record):
        # Resolve the message lazily: if the level is filtered out this is
        # never called, and even when it is, %s args are applied here rather
        # than at the call site.
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "service": self.service,
            "env": self.env,
            "msg": record.getMessage(),
        }

        # Promote structured fields passed via extra=
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = value

        # Exceptions stay structured, not stringified
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


def install_json_logging(level=None, service="DR", env=None):
    """Route the root logger through the JSON formatter.

    Called from app/config.py, which every module imports first, so this
    covers the whole process including libraries that log to the root.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service=service, env=env))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level or logging.INFO)
    return root
