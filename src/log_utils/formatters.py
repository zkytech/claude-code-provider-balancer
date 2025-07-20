"""Custom logging formatters."""

import dataclasses
import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


@dataclasses.dataclass
class LogError:
    name: str
    message: str
    stack_trace: Optional[str] = None
    args: Optional[Tuple[Any, ...]] = None


@dataclasses.dataclass 
class LogRecord:
    event: str
    message: str
    request_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[LogError] = None


class ColoredConsoleFormatter(logging.Formatter):
    """Console formatter with color support and simplified output for CLI."""

    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[95m', # Magenta
    }
    
    # Special colors for specific events (more subtle)
    # Empty dict - let all events use default level colors
    EVENT_COLORS = {}
    
    RESET = '\033[0m'

    def format(self, record: logging.LogRecord) -> str:
        # Get simplified output for console
        log_dict = self._get_simplified_log_dict(record)

        # Check if we should use colors (only for TTY output and when enabled)
        # Try to get settings from various locations
        use_colors = True  # Default to using colors
        try:
            # Try to import from main module
            import sys
            if 'main' in sys.modules:
                main_module = sys.modules['main']
                settings = getattr(main_module, 'settings', None)
                if settings and hasattr(settings, 'log_color'):
                    use_colors = settings.log_color
        except (ImportError, AttributeError):
            pass
        
        # Only use colors if TTY output is available
        use_colors = (
            use_colors
            and hasattr(sys.stdout, 'isatty')
            and sys.stdout.isatty()
        )

        if use_colors:
            # Check if this is a special event that should use a different color
            event = log_dict.get('event', '')
            if event in self.EVENT_COLORS:
                color = self.EVENT_COLORS[event]
            else:
                color = self.COLORS.get(record.levelname, '')
            
            formatted_json = json.dumps(log_dict, ensure_ascii=False)
            return f"{color}{formatted_json}{self.RESET}"
        else:
            return json.dumps(log_dict, ensure_ascii=False)

    def _get_simplified_log_dict(self, record: logging.LogRecord) -> dict:
        """Extract simplified log dictionary for console output."""
        log_payload = getattr(record, "log_record", None)
        
        if isinstance(log_payload, LogRecord):
            # For structured logs, create a simplified version
            # Truncate very long messages for console output
            message = log_payload.message
            if len(message) > 200:
                message = message[:200] + "..."
            
            simplified = {
                "time": datetime.fromtimestamp(record.created, timezone.utc).strftime("%H:%M:%S"),
                "level": record.levelname,
                "event": log_payload.event,
                "message": message
            }
            
            # Add request_id if present (useful for tracking)
            if log_payload.request_id:
                simplified["req_id"] = log_payload.request_id[:8]  # Short version
            
            # For errors/warnings, add simplified error info
            if log_payload.error and record.levelname in ['ERROR', 'WARNING', 'CRITICAL']:
                simplified["error"] = log_payload.error.name
                
                # Special handling for validation errors - make them much more concise
                if log_payload.error.name == "ValidationError":
                    # Extract just the count and field info for CLI
                    error_msg = log_payload.error.message
                    if "validation error" in error_msg:
                        # Extract error count from start of message
                        import re
                        count_match = re.match(r'(\d+) validation error', error_msg)
                        if count_match:
                            count = count_match.group(1)
                            simplified["error_msg"] = f"{count} validation errors (see log file for details)"
                        else:
                            simplified["error_msg"] = "Validation error (see log file for details)"
                    else:
                        simplified["error_msg"] = "Validation error (see log file for details)"
                elif log_payload.error.message != log_payload.message:
                    # For other errors, truncate long messages
                    simplified["error_msg"] = log_payload.error.message[:100]
            
            # Add critical data fields only for important events
            if log_payload.data and record.levelname in ['ERROR', 'CRITICAL']:
                # Only include essential fields like status_code, provider_name
                essential_fields = ['status_code', 'provider_name', 'provider_type', 'attempt']
                for field in essential_fields:
                    if field in log_payload.data:
                        simplified[field] = log_payload.data[field]
            
            return simplified
        else:
            # For non-structured logs, use basic format
            return {
                "time": datetime.fromtimestamp(record.created, timezone.utc).strftime("%H:%M:%S"),
                "level": record.levelname,
                "message": record.getMessage()
            }

    def _get_log_dict(self, record: logging.LogRecord) -> dict:
        """Extract log dictionary from record, similar to JSONFormatter logic."""
        header = {
            "timestamp": datetime.fromtimestamp(
                record.created, timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
        }
        log_payload = getattr(record, "log_record", None)
        if isinstance(log_payload, LogRecord):
            header["detail"] = dataclasses.asdict(log_payload)
        else:
            header["message"] = record.getMessage()
            if record.exc_info:
                exc_type, exc_value, exc_tb = record.exc_info
                header["error"] = {
                    "name": exc_type.__name__ if exc_type else "UnknownError",
                    "message": str(exc_value),
                    "stack_trace": "".join(
                        traceback.format_exception(exc_type, exc_value, exc_tb)
                    ),
                    "args": exc_value.args if hasattr(exc_value, "args") else [],
                }

        # Remove stack_trace for console output
        if (
            "detail" in header
            and "error" in header["detail"]
            and header["detail"]["error"]
        ):
            if "stack_trace" in header["detail"]["error"]:
                del header["detail"]["error"]["stack_trace"]
        elif "error" in header and header["error"]:
            if "stack_trace" in header["error"]:
                del header["error"]["stack_trace"]

        return header


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        header = {
            "timestamp": datetime.fromtimestamp(
                record.created, timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
        }
        log_payload = getattr(record, "log_record", None)
        if isinstance(log_payload, LogRecord):
            header["detail"] = dataclasses.asdict(log_payload)
        else:
            header["message"] = record.getMessage()
            if record.exc_info:
                exc_type, exc_value, exc_tb = record.exc_info
                header["error"] = {
                    "name": exc_type.__name__ if exc_type else "UnknownError",
                    "message": str(exc_value),
                    "stack_trace": "".join(
                        traceback.format_exception(exc_type, exc_value, exc_tb)
                    ),
                    "args": exc_value.args if hasattr(exc_value, "args") else [],
                }
        return json.dumps(header, ensure_ascii=False)


class ConsoleJSONFormatter(JSONFormatter):
    def format(self, record: logging.LogRecord) -> str:
        log_dict = json.loads(super().format(record))
        if (
            "detail" in log_dict
            and "error" in log_dict["detail"]
            and log_dict["detail"]["error"]
        ):
            if "stack_trace" in log_dict["detail"]["error"]:
                del log_dict["detail"]["error"]["stack_trace"]
        elif "error" in log_dict and log_dict["error"]:
            if "stack_trace" in log_dict["error"]:
                del log_dict["error"]["stack_trace"]
        return json.dumps(log_dict)


class UvicornAccessFormatter(logging.Formatter):
    """Special formatter for uvicorn access logs to match application log colors."""

    # light gray for info messages
    INFO_GRAY = '\033[56m'  # bright blue (more readable than dark gray)
    RESET = '\033[0m'
    
    def __init__(self):
        # Use a simple format that works with uvicorn's log message structure
        super().__init__(fmt="%(levelname)s:     %(message)s")
    
    def format(self, record: logging.LogRecord) -> str:
        # Format the record normally first
        formatted_message = super().format(record)
        
        # Check if colors should be used (only for TTY output)
        use_colors = (
            hasattr(sys, 'stdout') 
            and hasattr(sys.stdout, 'isatty') 
            and sys.stdout.isatty()
        )
        
        if use_colors:
            return f"{self.INFO_GRAY}{formatted_message}{self.RESET}"
        else:
            return formatted_message