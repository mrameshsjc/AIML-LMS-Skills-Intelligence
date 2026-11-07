"""
Logging set-up.

PURPOSE
    Give every log line the same readable format, including the request ID,
    so a problem can be traced from the API call to the exact error.

WHY THIS APPROACH
    Python's built-in `logging` module is used instead of `print()` because:
      - log levels (DEBUG, INFO, WARNING, ERROR) can be switched on/off with
        one setting (LOG_LEVEL in .env) without touching code;
      - every line gets a timestamp and the module name automatically;
      - Docker and cloud platforms collect anything written to the console,
        so console logging is all we need for now.
    A dedicated library (e.g. structlog, loguru) is not needed at this stage;
    it can be added later without changing how the rest of the code logs.

INPUT
    The log level, e.g. "INFO".
OUTPUT
    Configured root logger. Any module can then do:
        logger = logging.getLogger(__name__)
        logger.info("Something happened")

EXAMPLE OUTPUT LINE
    2026-11-07 10:30:01 | INFO     | app.main | req=3f2a9c1e | GET /api/v1/health -> 200 (2.1 ms)
"""

import logging
import sys
from contextvars import ContextVar

# A ContextVar holds a value per request, even when many requests run at the
# same time. The middleware in main.py sets it; the filter below reads it.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Add the current request ID to every log record as `record.request_id`."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True  # True = keep the record (we only add data, never drop)


LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | req=%(request_id)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger to write formatted lines to the console.

    Calling it twice is safe: existing handlers are replaced, so log lines are
    never printed twice (a common beginner problem with `--reload`).
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn has its own access log; ours (in main.py) includes the request
    # ID and timing, so we quieten uvicorn's copy to avoid duplicate lines.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
