"""
Structured JSON logging configuration.
"""

import dataclasses
import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from logging.config import dictConfig
from typing import Any, Dict, Optional

from rich.console import Console

from .config import settings

console = Console()


class JSONFormatter(logging.Formatter):
    """Formats log records as JSON Lines."""

    def format(self, record: logging.LogRecord) -> str:
        header = {
            "timestamp": datetime.fromtimestamp(
                record.created, timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
        }

        log_record = getattr(record, "log_record", None)
        if isinstance(log_record, LogRecord):
            header["detail"] = dataclasses.asdict(log_record)
        else:
            header["message"] = record.getMessage()

            if record.exc_info:
                exc_type, exc_value, exc_tb = record.exc_info
                header["error"] = {
                    "type": exc_type.__name__,
                    "message": str(exc_value),
                    "stack_trace": "".join(
                        traceback.format_exception(exc_type, exc_value, exc_tb)
                    ),
                }

        return json.dumps(header, ensure_ascii=False)


dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": JSONFormatter,
            }
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "": {
                "handlers": ["default"],
                "level": logging.WARN,
            },
            "claude_proxy": {
                "handlers": ["default"],
                "level": settings.log_level,
                "propagate": False,
            },
            "uvicorn": {
                "handlers": ["default"],
                "level": logging.WARN,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["default"],
                "level": logging.WARN,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["default"],
                "level": logging.WARN,
                "propagate": False,
            },
        },
    }
)


@dataclasses.dataclass
class LogRecord:
    """Standard structure for all application logs."""

    event: str
    message: str
    request_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


logger = logging.getLogger("claude_proxy")

if settings.log_file_path:
    try:
        log_dir = os.path.dirname(settings.log_file_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        file_handler = logging.FileHandler(settings.log_file_path, mode="a")
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to configure file logging: {e}", file=sys.stderr)


def log(level: int, record: LogRecord) -> None:
    """Log a structured record at the specified level."""
    logger.log(level=level, msg="", extra={"log_record": record})


def debug(record: LogRecord) -> None:
    """Log at DEBUG level."""
    log(logging.DEBUG, record)


def info(record: LogRecord) -> None:
    """Log at INFO level."""
    log(logging.INFO, record)


def warning(record: LogRecord) -> None:
    """Log at WARNING level."""
    log(logging.WARNING, record)


def error(record: LogRecord) -> None:
    """Log at ERROR level."""
    log(logging.ERROR, record)


def critical(record: LogRecord) -> None:
    """Log at CRITICAL level."""
    log(logging.CRITICAL, record)


def log_exception(
    message: str,
    exc: Exception,
    request_id: Optional[str] = None,
    event: str = "exception",
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """Log an exception with full traceback."""
    error_data = {
        "type": type(exc).__name__,
        "message": str(exc),
        "stack_trace": "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ),
    }

    record = LogRecord(
        event=event, message=message, request_id=request_id, data=data, error=error_data
    )

    error(record)
