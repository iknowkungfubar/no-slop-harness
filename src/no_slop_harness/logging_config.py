"""Structured logging configuration for the No-Slop Harness.

Provides JSON and console formatters, log level management,
and context-aware logging utilities for the CIV pipeline.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter for machine-readable output."""

    def __init__(self) -> None:
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON object."""
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])

        extra_fields = {
            k: v
            for k, v in record.__dict__.items()
            if k not in {
                "args", "asctime", "created", "exc_info", "exc_text",
                "filename", "funcName", "levelname", "levelno", "lineno",
                "module", "msecs", "message", "msg", "name", "pathname",
                "process", "processName", "relativeCreated", "stack_info",
                "thread", "threadName",
            }
        }
        if extra_fields:
            log_entry["extra"] = extra_fields

        return json.dumps(log_entry, default=str)


class PipelineLogger:
    """Context-aware logger that attaches pipeline metadata to every log entry.

    Usage:
        logger = PipelineLogger("orchestrator", request_id="abc-123")
        logger.info("Plan accepted", task_count=5)
    """

    def __init__(
        self,
        name: str,
        request_id: str | None = None,
        phase: str | None = None,
    ) -> None:
        self._logger = logging.getLogger(name)
        self.request_id = request_id
        self.phase = phase

    def _log(self, level: int, msg: str, **kwargs: Any) -> None:
        extra: dict[str, Any] = {}
        if self.request_id:
            extra["request_id"] = self.request_id
        if self.phase:
            extra["phase"] = self.phase
        extra.update(kwargs)
        self._logger.log(level, msg, extra=extra)

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, msg, **kwargs)

    def critical(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, msg, **kwargs)


def configure_logging(
    level: int = logging.INFO,
    json_output: bool = False,
    log_file: str | None = None,
) -> None:
    """Configure the root logger for the No-Slop Harness.

    Args:
        level: Logging level (default: INFO).
        json_output: If True, use JSONFormatter instead of plain text.
        log_file: Optional file path for log output.
    """
    root = logging.getLogger("no_slop_harness")
    root.setLevel(level)

    # Remove existing handlers to avoid duplicates on reconfiguration
    root.handlers.clear()

    if json_output:
        formatter: logging.Formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    if log_file:
        handler: logging.Handler = logging.FileHandler(log_file)
    else:
        handler = logging.StreamHandler(sys.stderr)

    handler.setFormatter(formatter)
    root.addHandler(handler)

    # Quiet noisy third-party loggers
    for noisy in ("urllib3", "httpx", "httpcore", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
