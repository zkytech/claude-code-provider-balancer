"""Logging handlers and utility functions."""

import enum
import logging
import traceback
from typing import Optional

from .formatters import LogError, LogRecord


class LogEvent(enum.Enum):
    # Core request flow events
    MODEL_SELECTION = "model_selection"
    REQUEST_START = "request_start"
    REQUEST_COMPLETED = "request_completed"
    REQUEST_FAILURE = "request_failure"
    REQUEST_RECEIVED = "request_received"
    CLIENT_REQUEST_DEBUG = "client_request_debug"
    
    # Provider communication events
    UPSTREAM_REQUEST = "upstream_request"
    PROVIDER_REQUEST = "provider_request"
    PROVIDER_REQUEST_ERROR = "provider_request_error"
    PROVIDER_HTTP_ERROR_DETAILS = "provider_http_error_details"
    PROVIDER_API_ERROR_DETAILS = "provider_api_error_details"
    PROVIDER_LOADED = "provider_loaded"
    PROVIDER_FALLBACK = "provider_fallback"
    ALL_PROVIDERS_FAILED = "all_providers_failed"
    ERROR_NOT_RETRYABLE = "error_not_retryable"
    GET_PROVIDER_HEADERS_START = "get_provider_headers_start"
    
    # Response processing events
    OPENAI_RESPONSE = "openai_response"
    ANTHROPIC_RESPONSE = "anthropic_response"
    
    # Streaming events
    STREAMING_REQUEST = "streaming_request"
    STREAM_INTERRUPTED = "stream_interrupted"
    SSE_EXTRACTION_COMPLETE = "sse_extraction_complete"
    
    # Token counting events
    TOKEN_COUNT = "token_count"
    TOKEN_ENCODER_LOAD_FAILED = "token_encoder_load_failed"
    
    # Message processing events
    SYSTEM_PROMPT_ADJUSTED = "system_prompt_adjusted"
    MESSAGE_FORMAT_NORMALIZED = "message_format_normalized"
    
    # Tool processing events
    TOOL_INPUT_SERIALIZATION_FAILURE = "tool_input_serialization_failure"
    TOOL_RESULT_SERIALIZATION_FAILURE = "tool_result_serialization_failure"
    TOOL_RESULT_PROCESSING = "tool_result_processing"
    TOOL_CHOICE_UNSUPPORTED = "tool_choice_unsupported"
    TOOL_ARGS_TYPE_MISMATCH = "tool_args_type_mismatch"
    TOOL_ARGS_PARSE_FAILURE = "tool_args_parse_failure"
    TOOL_ARGS_UNEXPECTED = "tool_args_unexpected"
    TOOL_ID_PLACEHOLDER = "tool_id_placeholder"
    TOOL_ID_UPDATED = "tool_id_updated"
    
    # System events
    IMAGE_FORMAT_UNSUPPORTED = "image_format_unsupported"
    PARAMETER_UNSUPPORTED = "parameter_unsupported"
    HEALTH_CHECK = "health_check"
    PROVIDER_ERROR_DETAILS = "provider_error_details"
    FASTAPI_STARTUP_COMPLETE = "fastapi_startup_complete"
    FASTAPI_SHUTDOWN = "fastapi_shutdown"
    HTTP_REQUEST = "http_request"
    
    # OAuth events
    OAUTH_KEYRING_UNAVAILABLE = "oauth_keyring_unavailable"
    OAUTH_TOKENS_SAVED = "oauth_tokens_saved"
    OAUTH_SAVE_FAILED = "oauth_save_failed"
    OAUTH_TOKENS_SAVED_ASYNC = "oauth_tokens_saved_async"
    OAUTH_SAVE_FAILED_ASYNC = "oauth_save_failed_async"
    OAUTH_NO_TOKENS_FOUND = "oauth_no_tokens_found"
    OAUTH_TOKENS_LOADED = "oauth_tokens_loaded"
    OAUTH_LOAD_FAILED = "oauth_load_failed"
    OAUTH_TOKENS_CLEANED = "oauth_tokens_cleaned"
    OAUTH_TOKENS_SAVED_AFTER_CLEANUP = "oauth_tokens_saved_after_cleanup"
    OAUTH_SAVE_FAILED_AFTER_CLEANUP = "oauth_save_failed_after_cleanup"
    OAUTH_URL_GENERATED = "oauth_url_generated"
    OAUTH_URL_DEBUG = "oauth_url_debug"
    OAUTH_NO_STATE = "oauth_no_state"
    OAUTH_STATE_EXPIRED = "oauth_state_expired"
    OAUTH_TOKEN_EXCHANGE_FAILED = "oauth_token_exchange_failed"
    OAUTH_DUPLICATE_FOUND_EMAIL = "oauth_duplicate_found_email"
    OAUTH_DUPLICATE_FOUND_TOKEN = "oauth_duplicate_found_token"
    OAUTH_DUPLICATE_FOUND_REFRESH = "oauth_duplicate_found_refresh"
    OAUTH_DUPLICATE_FOUND_FINGERPRINT = "oauth_duplicate_found_fingerprint"
    OAUTH_DUPLICATE_FOUND_ACCOUNT = "oauth_duplicate_found_account"
    OAUTH_TOKEN_REMOVED = "oauth_token_removed"
    OAUTH_TOKEN_ADDED = "oauth_token_added"
    OAUTH_TOKENS_SAVED_AFTER_EXCHANGE = "oauth_tokens_saved_after_exchange"
    OAUTH_SAVE_FAILED_AFTER_EXCHANGE = "oauth_save_failed_after_exchange"
    OAUTH_EXCHANGE_SUCCESS = "oauth_exchange_success"
    OAUTH_TOKEN_EXPIRY = "oauth_token_expiry"
    OAUTH_AUTO_REFRESH_STARTED = "oauth_auto_refresh_started"
    OAUTH_EXCHANGE_ERROR = "oauth_exchange_error"
    OAUTH_REFRESH_REQUEST = "oauth_refresh_request"
    OAUTH_REFRESH_RESPONSE_STATUS = "oauth_refresh_response_status"
    OAUTH_REFRESH_RESPONSE_TEXT = "oauth_refresh_response_text"
    OAUTH_REFRESH_FAILED = "oauth_refresh_failed"
    OAUTH_REFRESH_SUCCESSFUL = "oauth_refresh_successful"
    OAUTH_TOKEN_REFRESHED = "oauth_token_refreshed"
    OAUTH_NEW_TOKEN_EXPIRY = "oauth_new_token_expiry"
    OAUTH_REFRESH_ERROR = "oauth_refresh_error"
    OAUTH_TOKEN_USED = "oauth_token_used"
    OAUTH_ALL_TOKENS_INVALID = "oauth_all_tokens_invalid"
    OAUTH_TOKEN_NEEDS_REFRESH = "oauth_token_needs_refresh"
    OAUTH_AUTO_REFRESH_FAILED = "oauth_auto_refresh_failed"
    OAUTH_NEXT_REFRESH_SCHEDULED = "oauth_next_refresh_scheduled"
    OAUTH_AUTO_REFRESH_CANCELLED = "oauth_auto_refresh_cancelled"
    OAUTH_AUTO_REFRESH_LOOP_ERROR = "oauth_auto_refresh_loop_error"
    OAUTH_REFRESH_BY_EMAIL_NOT_FOUND = "oauth_refresh_by_email_not_found"
    OAUTH_REFRESH_BY_EMAIL_NO_REFRESH_TOKEN = "oauth_refresh_by_email_no_refresh_token"
    OAUTH_REFRESH_BY_EMAIL_START = "oauth_refresh_by_email_start"
    OAUTH_REFRESH_BY_EMAIL_SUCCESS = "oauth_refresh_by_email_success"
    OAUTH_REFRESH_BY_EMAIL_FAILED = "oauth_refresh_by_email_failed"
    OAUTH_TOKEN_REMOVED_BY_EMAIL = "oauth_token_removed_by_email"
    OAUTH_TOKENS_SAVED_AFTER_REMOVAL = "oauth_tokens_saved_after_removal"
    OAUTH_SAVE_FAILED_AFTER_REMOVAL = "oauth_save_failed_after_removal"
    OAUTH_ALL_TOKENS_CLEARED = "oauth_all_tokens_cleared"
    OAUTH_TOKENS_SAVED_AFTER_CLEAR = "oauth_tokens_saved_after_clear"
    OAUTH_SAVE_FAILED_AFTER_CLEAR = "oauth_save_failed_after_clear"
    OAUTH_EXISTING_TOKENS_FOUND = "oauth_existing_tokens_found"
    OAUTH_MANAGER_INITIALIZED = "oauth_manager_initialized"
    OAUTH_AUTO_REFRESH_ALL_STARTED = "oauth_auto_refresh_all_started"
    OAUTH_AUTO_REFRESH_DISABLED = "oauth_auto_refresh_disabled"
    OAUTH_MANAGER_READY = "oauth_manager_ready"
    OAUTH_AUTO_REFRESH_START_FAILED = "oauth_auto_refresh_start_failed"
    OAUTH_URL_GENERATION_ERROR = "oauth_url_generation_error"
    OAUTH_MANUAL_REFRESH_ERROR = "oauth_manual_refresh_error"
    OAUTH_MANAGER_CHECK = "oauth_manager_check"


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


def error_file_only(record: LogRecord, exc: Optional[Exception] = None):
    """Log an error message only to file, not to console."""
    try:
        if _logger is None:
            init_logger()
        
        # Create a copy of the logger with only file handler
        file_logger = logging.getLogger(f"{_logger.name}.file_only")
        
        # Remove all existing handlers to prevent console output
        file_logger.handlers.clear()
        file_logger.propagate = False
        
        # Add only file handler if it exists in the main logger
        for handler in _logger.handlers:
            if isinstance(handler, logging.FileHandler):
                file_logger.addHandler(handler)
                break
        
        # If no file handler found, try to get it from parent logger
        if not file_logger.handlers and _logger.parent:
            for handler in _logger.parent.handlers:
                if isinstance(handler, logging.FileHandler):
                    file_logger.addHandler(handler)
                    break
        
        # Process the log record similar to _log function
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

        # Log only to file
        if file_logger.handlers:
            file_logger.error(record.message, extra={"log_record": record})
        else:
            # Fallback: if no file handler available, log to main logger with a marker
            record.message = f"[FILE_ONLY] {record.message}"
            _log(logging.ERROR, record, exc=exc)
            
    except Exception:
        # Fallback to regular error logging
        error(record, exc=exc)