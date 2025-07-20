"""Logging functionality and custom formatters."""

from .formatters import (
    LogError,
    LogRecord,
    ColoredConsoleFormatter,
    JSONFormatter,
    ConsoleJSONFormatter
)

from .handlers import (
    LogEvent,
    init_logger,
    debug,
    info,
    warning,
    error,
    critical
)

__all__ = [
    "LogError",
    "LogRecord",
    "ColoredConsoleFormatter",
    "JSONFormatter", 
    "ConsoleJSONFormatter",
    "LogEvent",
    "init_logger",
    "debug",
    "info",
    "warning",
    "error",
    "critical"
]