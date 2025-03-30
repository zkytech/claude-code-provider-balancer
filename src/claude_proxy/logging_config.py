"""
JSON Lines logging configuration and utilities.
"""
import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union
from rich.console import Console
from rich.syntax import Syntax
from rich.pretty import pretty_repr
from .config import settings

SENSITIVE_HEADERS = {
    'authorization', 'api-key', 'x-api-key', 'proxy-authorization', 
    'openrouter-api-key'
}

class JSONFormatter(logging.Formatter):
    """Formats log records as JSON Lines."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Convert log record to JSON string."""
        data = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
        }
        
        if hasattr(record, 'request_id'):
            data['request_id'] = record.request_id
            
        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            data['error'] = {
                'type': exc_type.__name__,
                'message': str(exc_value),
                'stack_trace': ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
            }
        
        if hasattr(record, 'structured_data') and isinstance(record.structured_data, dict):
            data.update(record.structured_data)
        else:
            data['message'] = record.getMessage()
            
        if record.args and isinstance(record.args, dict):
            data.update(record.args)
            
        return json.dumps(data, ensure_ascii=False)

logging.basicConfig(level="WARNING")

logger = logging.getLogger("claude_proxy")
logger.setLevel(settings.log_level)
logger.propagate = False

payload_logger = logging.getLogger("claude_proxy.http")
payload_logger.setLevel(logging.DEBUG)
payload_logger.propagate = False

console = Console()

try:
    log_dir = os.path.dirname(settings.log_file_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        
    file_handler = logging.FileHandler(settings.log_file_path, mode='a')
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)
    
    if settings.log_file_path:
        payload_dir = os.path.dirname(settings.log_file_path)
        if payload_dir:
            os.makedirs(payload_dir, exist_ok=True)
        payload_handler = logging.FileHandler(settings.log_file_path, mode='a')
        payload_handler.setFormatter(JSONFormatter())
        payload_logger.addHandler(payload_handler)
    
    
except Exception as e:
    print(f"Failed to configure file logging: {e}", file=sys.stderr)

def format_for_console(obj):
    """Format object for console display."""
    if obj is None:
        return None
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return pretty_repr(obj)


def log_json_body(title: str, data_obj: Any, request_id: str, color="dim"):
    """Logs a Python object as JSON (DEBUG level only)."""
    if logger.level > logging.DEBUG:
        return
    try:
        logger.debug(
            f"JSON payload: {title}",
            extra={
                "request_id": request_id,
                "structured_data": {
                    "event": "json_payload",
                    "payload_type": title,
                    "payload": data_obj
                }
            }
        )
    except Exception as e:
        logger.error(
            f"Error logging JSON body",
            extra={
                "request_id": request_id,
                "structured_data": {
                    "event": "log_error",
                    "payload_type": title,
                    "error": str(e)
                }
            }
        )


def log_request_start(
    request_id: str, client_model: str, target_model: str, stream: bool
):
    """Logs the start of an API request."""
    logger.info(
        "Request started",
        extra={
            "request_id": request_id,
            "structured_data": {
                "event": "request_start",
                "client_model": client_model,
                "target_model": target_model,
                "stream": stream
            }
        }
    )


def log_request_end(
    request_id: str, status_code: int, duration_ms: float, usage: dict | None = None
):
    """Logs the successful end of an API request."""
    data = {
        "event": "request_end",
        "status_code": status_code,
        "duration_ms": duration_ms
    }
    
    if usage:
        data["input_tokens"] = usage.get("input_tokens")
        data["output_tokens"] = usage.get("output_tokens")
    
    logger.info(
        "Request completed",
        extra={
            "request_id": request_id,
            "structured_data": data
        }
    )


def log_error_simplified(
    request_id: str, exc: Exception, status_code: int, duration_ms: float, detail: str
):
    """Logs error summary with structured data."""
    error_type = type(exc).__name__
    
    logger.error(
        "Request error",
        exc_info=exc,
        extra={
            "request_id": request_id,
            "structured_data": {
                "event": "request_error",
                "status_code": status_code,
                "duration_ms": duration_ms,
                "error_type": error_type,
                "error_detail": detail
            }
        }
    )

def _mask_sensitive_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Mask sensitive header values."""
    if not headers:
        return {}
    return {
        k: '***MASKED***' if k.lower() in SENSITIVE_HEADERS else v
        for k, v in headers.items()
    }

def log_http_interaction(
    step_name: str,
    request_id: str,
    *,
    method: Optional[str] = None,
    url: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Union[bytes, str, dict]] = None,
    status_code: Optional[int] = None,
    elapsed_ms: Optional[float] = None,
) -> None:
    """Log detailed HTTP interaction to the payload log file."""
    if not settings.log_file_path:
        logger.debug(
            "Payload logging disabled",
            extra={
                "request_id": request_id,
                "structured_data": {
                    "event": "payload_logging_disabled",
                    "reason": "no_file_path"
                }
            }
        )
        return
    if not payload_logger.handlers:
        logger.debug(
            "Payload logging disabled",
            extra={
                "request_id": request_id,
                "structured_data": {
                    "event": "payload_logging_disabled",
                    "reason": "no_handlers"
                }
            }
        )
        return
    
    try:
        entry = {
            "event": "http_interaction",
            "step": step_name,
            "method": method,
            "url": url,
            "headers": _mask_sensitive_headers(headers) if headers else None,
            "status_code": status_code,
            "elapsed_ms": elapsed_ms,
        }

        if isinstance(body, (dict, list)):
            entry["body"] = body
        elif isinstance(body, str):
            try:
                entry["body"] = json.loads(body)
            except json.JSONDecodeError:
                entry["body"] = {"_type": "string", "content": body}
        elif isinstance(body, bytes):
            try:
                decoded = body.decode('utf-8')
                entry["body"] = json.loads(decoded)
            except (UnicodeDecodeError, json.JSONDecodeError):
                import base64
                entry["body"] = {
                    "_type": "bytes",
                    "base64": base64.b64encode(body).decode('ascii')
                }
        elif body is not None:
            entry["body"] = {
                "_type": type(body).__name__,
                "repr": str(body)
            }

        payload_logger.debug(
            "HTTP interaction",
            extra={
                "request_id": request_id,
                "structured_data": entry
            }
        )
    except Exception as e:
        logger.error(
            "Failed to write payload log entry",
            extra={
                "request_id": request_id,
                "structured_data": {
                    "event": "payload_log_error",
                    "error": str(e)
                }
            }
        )
