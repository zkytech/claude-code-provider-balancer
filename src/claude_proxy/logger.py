"""
Structured JSON logging configuration.
"""

import dataclasses
import enum
import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from logging.config import dictConfig
from typing import Any, Dict, Optional, Tuple

from rich.console import Console

from .config import settings

console = Console()
error_console = Console(stderr=True, style="bold red")


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
                    "name": exc_type.__name__,
                    "message": str(exc_value),
                    "stack_trace": "".join(
                        traceback.format_exception(exc_type, exc_value, exc_tb)
                    ),
                    "args": exc_value.args,
                }

        return json.dumps(header, ensure_ascii=False)


class ConsoleJSONFormatter(JSONFormatter):
    """JSON formatter for console that excludes stack traces."""

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
            log_record_dict = dataclasses.asdict(log_record)
            if log_record_dict.get("error"):
                if log_record_dict["error"].get("stack_trace"):
                    log_record_dict["error"].pop("stack_trace", None)

            header["detail"] = log_record_dict
        else:
            header["message"] = record.getMessage()

            if record.exc_info:
                exc_type, exc_value, _ = record.exc_info
                header["error"] = {
                    "name": exc_type.__name__,
                    "message": str(exc_value),
                    "args": exc_value.args,
                }

        return json.dumps(header, ensure_ascii=False)


dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": JSONFormatter,
            },
            "console_json": {
                "()": ConsoleJSONFormatter,
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "console_json",
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


class LogEvent(enum.Enum):
    """All possible log event types for structured logging."""

    MODEL_SELECTION = "model_selection"
    REQUEST_START = "request_start"
    REQUEST_COMPLETED = "request_completed"
    REQUEST_VALIDATION = "request_validation"
    PROVIDER_IDENTIFICATION = "provider_identification"
    OPENAI_REQUEST = "openai_request"
    OPENAI_RESPONSE = "openai_response"
    ANTHROPIC_RESPONSE = "anthropic_response"
    STREAMING_REQUEST = "streaming_request"
    TOKEN_COUNT = "token_count"
    PROVIDER_ERROR_RESPONSE = "provider_error_response"
    CONVERSION_FAILURE = "conversion_failure"
    TOOL_HANDLING = "tool_handling"
    RATE_LIMIT = "rate_limit"
    CONFIG_INVALID = "config_invalid"
    NETWORK_ERROR = "network_error"
    REQUEST_FAILURE = "request_failure"
    SYSTEM_PROMPT_ADJUSTED = "system_prompt_adjusted"
    TOOL_INPUT_SERIALIZATION_FAILURE = "tool_input_serialization_failure"
    IMAGE_FORMAT_UNSUPPORTED = "image_format_unsupported"
    MESSAGE_FORMAT_NORMALIZED = "message_format_normalized"
    TOOL_RESULT_SERIALIZATION_FAILURE = "tool_result_serialization_failure"
    TOOL_CHOICE_UNSUPPORTED = "tool_choice_unsupported"
    TOOL_ARGS_TYPE_MISMATCH = "tool_args_type_mismatch"
    TOOL_ARGS_PARSE_FAILURE = "tool_args_parse_failure"
    TOOL_ARGS_UNEXPECTED = "tool_args_unexpected"
    TOOL_ID_PLACEHOLDER = "tool_id_placeholder"
    TOOL_ID_UPDATED = "tool_id_updated"
    STREAM_INTERRUPTED = "stream_interrupted"
    PARAMETER_UNSUPPORTED = "parameter_unsupported"
    HEALTH_CHECK = "health_check"


@dataclasses.dataclass
class LogError:
    name: str
    message: str
    stack_trace: str
    args: Tuple[Any, ...]


@dataclasses.dataclass
class LogRecord:
    """Standard structure for all application logs."""

    event: str
    message: str
    request_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[LogError] = None


_logger = logging.getLogger("claude_proxy")

if settings.log_file_path:
    try:
        log_dir = os.path.dirname(settings.log_file_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        file_handler = logging.FileHandler(settings.log_file_path, mode="a")
        file_handler.setFormatter(JSONFormatter())
        _logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to configure file logging: {e}", file=sys.stderr)


def log(level: int, record: LogRecord) -> None:
    """Log a structured record at the specified level."""
    if type(record) is str:
        return _logger.log(level=level, msg=record)

    return _logger.log(level=level, msg="", extra={"log_record": record})


def debug(record: LogRecord) -> None:
    """Log at DEBUG level."""
    log(logging.DEBUG, record)


def info(record: LogRecord) -> None:
    """Log at INFO level."""
    log(logging.INFO, record)


def warning(record: LogRecord) -> None:
    """Log at WARNING level."""
    log(logging.WARNING, record)


def error(record: LogRecord, exc: Optional[Exception] = None) -> None:
    """Log at ERROR level with optional exception."""
    if exc is not None:
        error_console.print_exception(show_locals=True, width=120)
        record.error = {
            "name": type(exc).__name__,
            "message": str(exc),
            "stack_trace": "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ),
            "args": exc.args,
        }
        if not record.message:
            record.message = str(exc)
    log(logging.ERROR, record)


def critical(record: LogRecord) -> None:
    """Log at CRITICAL level."""
    log(logging.CRITICAL, record)
