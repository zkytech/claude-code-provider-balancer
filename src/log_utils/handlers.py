"""Logging handlers and utility functions."""

import enum
import logging
import traceback
from typing import Optional

from .formatters import LogError, LogRecord


class LogEvent(enum.Enum):
    MODEL_SELECTION = "model_selection"
    REQUEST_START = "request_start"
    REQUEST_COMPLETED = "request_completed"
    REQUEST_FAILURE = "request_failure"
    UPSTREAM_REQUEST = "upstream_request"
    OPENAI_RESPONSE = "openai_response"
    ANTHROPIC_RESPONSE = "anthropic_response"
    STREAMING_REQUEST = "streaming_request"
    STREAM_INTERRUPTED = "stream_interrupted"
    TOKEN_COUNT = "token_count"
    TOKEN_ENCODER_LOAD_FAILED = "token_encoder_load_failed"
    SYSTEM_PROMPT_ADJUSTED = "system_prompt_adjusted"
    TOOL_INPUT_SERIALIZATION_FAILURE = "tool_input_serialization_failure"
    IMAGE_FORMAT_UNSUPPORTED = "image_format_unsupported"
    MESSAGE_FORMAT_NORMALIZED = "message_format_normalized"
    TOOL_RESULT_SERIALIZATION_FAILURE = "tool_result_serialization_failure"
    TOOL_RESULT_PROCESSING = "tool_result_processing"
    TOOL_CHOICE_UNSUPPORTED = "tool_choice_unsupported"
    TOOL_ARGS_TYPE_MISMATCH = "tool_args_type_mismatch"
    TOOL_ARGS_PARSE_FAILURE = "tool_args_parse_failure"
    TOOL_ARGS_UNEXPECTED = "tool_args_unexpected"
    TOOL_ID_PLACEHOLDER = "tool_id_placeholder"
    TOOL_ID_UPDATED = "tool_id_updated"
    PARAMETER_UNSUPPORTED = "parameter_unsupported"
    HEALTH_CHECK = "health_check"
    PROVIDER_ERROR_DETAILS = "provider_error_details"
    REQUEST_RECEIVED = "request_received"


# Initialize logger - will be set up when module is initialized
_logger = None


def init_logger(app_name: str = "claude-provider-balancer"):
    """Initialize the logger for this module."""
    global _logger
    _logger = logging.getLogger(app_name)


def _log(level: int, record: LogRecord, exc: Optional[Exception] = None) -> None:
    """Internal logging function."""
    if _logger is None:
        init_logger()
    
    try:
        if exc:
            try:
                record.error = LogError(
                    name=type(exc).__name__,
                    message=str(exc),
                    stack_trace="".join(
                        traceback.format_exception(type(exc), exc, exc.__traceback__)
                    ),
                    args=exc.args if hasattr(exc, "args") else tuple(),
                )
            except Exception:
                # If error processing fails, create minimal error info
                record.error = LogError(
                    name="ProcessingError",
                    message="Error occurred during exception processing",
                    stack_trace="",
                    args=tuple(),
                )

            if not record.message and str(exc):
                try:
                    record.message = str(exc)
                except Exception:
                    record.message = "An error occurred but message could not be extracted"
            elif not record.message:
                record.message = "An unspecified error occurred"

        _logger.log(level=level, msg=record.message, extra={"log_record": record})
    except Exception:
        # Last resort: use standard Python logging without custom formatting
        try:
            import logging as std_logging
            std_logging.getLogger("fallback").log(level, f"Log error: {record.message}")
        except Exception:
            pass  # Silent failure to prevent infinite recursion


def debug(record: LogRecord):
    """Log a debug message."""
    _log(logging.DEBUG, record)


def info(record: LogRecord):
    """Log an info message."""
    _log(logging.INFO, record)


def warning(record: LogRecord, exc: Optional[Exception] = None):
    """Log a warning message."""
    _log(logging.WARNING, record, exc=exc)


def error(record: LogRecord, exc: Optional[Exception] = None):
    """Log an error message."""
    try:
        # Note: Console traceback printing is disabled to keep console output clean
        # Full traceback details are still logged to file
        _log(logging.ERROR, record, exc=exc)
    except Exception:
        # Last resort: use standard Python logging
        try:
            import logging as std_logging
            std_logging.getLogger("fallback").error(f"Error logging failed: {record.message}")
        except Exception:
            pass  # Silent failure to prevent infinite recursion


def critical(record: LogRecord, exc: Optional[Exception] = None):
    """Log a critical message."""
    _log(logging.CRITICAL, record, exc=exc)