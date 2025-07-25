"""
Claude Code Provider Balancer - Main Application Entry Point (Refactored)

Refactored modular FastAPI application with separated concerns:
- Routers: API endpoint definitions
- Handlers: Business logic
- Core: Provider management, streaming, etc.
"""

import json
import os
import sys
import time
import yaml
from pathlib import Path
from contextlib import asynccontextmanager

import fastapi
import uvicorn
from dotenv import load_dotenv
from fastapi import Request
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

# Add current directory to path for direct execution
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import core components
from core.provider_manager import ProviderManager
from oauth import init_oauth_manager, start_oauth_auto_refresh
from utils import (
    LogRecord, ColoredConsoleFormatter, JSONFormatter,
    init_logger, info, warning
)

# Import routers
from routers.messages import create_messages_router
from routers.oauth import create_oauth_router
from routers.health import create_health_router
from routers.management import create_management_router

load_dotenv()

# Initialize rich console for startup display
_console = Console()


def load_global_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from config.yaml"""
    if not os.path.isabs(config_path):
        # Look for config in project root (one level up from src)
        current_dir = Path(__file__).parent
        project_root = current_dir.parent
        config_path = project_root / config_path
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Failed to load config file: {e}")
        return {}


def _initialize_oauth_manager(provider_manager_instance: ProviderManager, is_reload: bool = False) -> bool:
    """
    Initialize or re-initialize OAuth manager with provider configuration.
    
    Args:
        provider_manager_instance: The provider manager instance with settings
        is_reload: Whether this is a config reload (affects logging messages)
    
    Returns:
        bool: True if initialization was successful, False otherwise
    """
    try:
        # Check if OAuth manager already exists with tokens before calling init
        from oauth import oauth_manager
        had_existing_tokens = oauth_manager and oauth_manager.token_credentials
        
        result_manager = init_oauth_manager(provider_manager_instance.settings)
        
        # Only log success if we actually did initialization (not skipped due to existing tokens)
        if not had_existing_tokens:
            event_name = "oauth_manager_reinitialized" if is_reload else "oauth_manager_ready"
            message = "OAuth manager re-initialized after config reload" if is_reload else "OAuth manager initialization completed successfully"
            
            info(LogRecord(
                event=event_name,
                message=message
            ))
        
        return True
    except Exception as e:
        event_name = "oauth_manager_reinit_failed" if is_reload else "oauth_manager_init_failed"
        message = f"Failed to re-initialize OAuth manager after config reload: {e}" if is_reload else f"Failed to initialize OAuth manager: {str(e)}"
        
        from utils import error
        error(LogRecord(
            event=event_name,
            message=message
        ))
        return False


class Settings:
    """Application settings loaded from provider config only."""

    def __init__(self):
        # Default values
        self.log_level: str = "INFO"
        self.log_file_path: str = ""
        self.log_color: bool = True
        self.providers_config_path: str = "config.yaml"
        self.referrer_url: str = "http://localhost:8082/claude_proxy"
        self.host: str = "127.0.0.1"
        self.port: int = 9090
        self.app_name: str = "Claude Code Provider Balancer"
        self.app_version: str = "0.6.0"
        
    def load_from_provider_config(self, config_path: str = "config.yaml"):
        """Load settings from provider configuration file"""
        # Determine the absolute path to the config file
        if not os.path.isabs(config_path):
            # If relative path, look for it in project root (one level up from src)
            current_dir = Path(__file__).parent
            project_root = current_dir.parent
            config_path = project_root / config_path
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # Load settings from the config file
            settings_config = config.get('settings', {})
            
            # Update settings from config
            for key, value in settings_config.items():
                if hasattr(self, key):
                    # Special handling for log file path to resolve relative to project root
                    if key == "log_file_path" and value and not os.path.isabs(value):
                        current_dir = Path(__file__).parent
                        project_root = current_dir.parent
                        value = str(project_root / value)
                    setattr(self, key, value)
                    
        except Exception as e:
            print(f"Warning: Failed to load settings from {config_path}: {e}")
            print("Using default settings.")


# Initialize provider manager and settings
try:
    provider_manager = ProviderManager()
    settings = Settings()
    
    # Load settings from provider config file
    settings.load_from_provider_config()
    
    # Initialize OAuth manager with config settings
    _initialize_oauth_manager(provider_manager, is_reload=False)
    
    # Set provider manager reference for deduplication module
    from caching.deduplication import set_provider_manager
    set_provider_manager(provider_manager)
    
except Exception as e:
    # Fallback to basic settings if provider config fails
    print(f"Warning: Failed to load provider configuration: {e}")
    print("Using basic settings...")
    provider_manager = None
    settings = Settings()
    
    # Still set the provider manager reference (even if None)
    from caching.deduplication import set_provider_manager
    set_provider_manager(provider_manager)

# Global config instance
global_config = load_global_config()

# Initialize logging
init_logger(settings.app_name)

# Setup logging configuration
import logging
from logging.config import dictConfig

log_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "colored_console": {
            "()": ColoredConsoleFormatter,
        },
        "json": {
            "()": JSONFormatter,
        },
        "uvicorn_access": {
            "()": "utils.logging.formatters.UvicornAccessFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": settings.log_level,
            "formatter": "colored_console",
            "stream": "ext://sys.stdout",
        },
        "uvicorn_access": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "uvicorn_access",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        settings.app_name: {
            "level": settings.log_level,
            "handlers": ["console"],
            "propagate": False,
        },
        "uvicorn.access": {
            "level": "INFO",
            "handlers": ["uvicorn_access"],
            "propagate": False,
        },
    },
}

# Add file handler if log_file_path is configured
if settings.log_file_path:
    log_config["handlers"]["file"] = {
        "class": "logging.FileHandler",
        "level": settings.log_level,
        "formatter": "json",
        "filename": settings.log_file_path,
        "mode": "a",
        "encoding": "utf-8",
    }
    log_config["loggers"][settings.app_name]["handlers"].append("file")

dictConfig(log_config)


@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    """FastAPI lifespan event handler"""
    # Startup
    info(LogRecord(
        event="fastapi_startup_complete",
        message="FastAPI application startup complete"
    ))
    info(LogRecord(
        event="oauth_manager_ready",
        message="OAuth manager ready for Claude Code Official authentication"
    ))
    
    # Start auto-refresh for any loaded OAuth tokens
    try:
        # Get auto-refresh setting from provider manager
        auto_refresh_enabled = provider_manager.oauth_auto_refresh_enabled if provider_manager else True
        await start_oauth_auto_refresh(auto_refresh_enabled)
    except Exception as e:
        warning(LogRecord(
            event="oauth_auto_refresh_start_failed",
            message=f"Failed to start OAuth auto-refresh: {e}"
        ))
    
    yield
    
    # Shutdown
    info(LogRecord(
        event="fastapi_shutdown",
        message="FastAPI application shutting down"
    ))


# Create FastAPI app
app = fastapi.FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Intelligent load balancer and failover proxy for Claude Code providers",
    lifespan=lifespan,
)

# Register routers
app.include_router(create_messages_router(provider_manager, settings))
app.include_router(create_oauth_router(provider_manager))
app.include_router(create_health_router(provider_manager, settings.app_name, settings.app_version))
app.include_router(create_management_router(provider_manager))

# Exception handlers
@app.exception_handler(ValidationError)
async def pydantic_validation_error_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation errors."""
    import uuid
    from handlers.message_handler import MessageHandler
    handler = MessageHandler(provider_manager, settings)
    request_id = str(uuid.uuid4())
    return await handler._log_and_return_error_response(request, exc, request_id, 400)


@app.exception_handler(json.JSONDecodeError)
async def json_decode_error_handler(request: Request, exc: json.JSONDecodeError):
    """Handle JSON decode errors."""
    import uuid
    from handlers.message_handler import MessageHandler
    handler = MessageHandler(provider_manager, settings)
    request_id = str(uuid.uuid4())
    return await handler._log_and_return_error_response(request, exc, request_id, 400)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle generic exceptions."""
    import uuid
    from handlers.message_handler import MessageHandler
    handler = MessageHandler(provider_manager, settings)
    request_id = str(uuid.uuid4())
    return await handler._log_and_return_error_response(request, exc, request_id, 500)


# Logging middleware
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Log all requests and responses."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    from utils import debug
    debug(
        LogRecord(
            event="http_request",
            message=f"{request.method} {request.url.path}",
            data={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time": round(process_time, 3),
            },
        )
    )
    
    return response


# Set function reference for deduplication module after all functions are defined
def _init_deduplication_references():
    """Initialize function references for deduplication module"""
    from caching.deduplication import set_make_anthropic_request
    from handlers.message_handler import MessageHandler
    handler = MessageHandler(provider_manager, settings)
    set_make_anthropic_request(handler.make_anthropic_request)

# Call initialization
_init_deduplication_references()


def _display_startup_banner():
    """Display startup banner with configuration info."""
    # Display ASCII art banner
    banner = """
══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
 ▄████▄ ██       ▄███▄  ██    ██ ██████  ███████     ██████   ▄███▄  ██       ▄███▄  ███    ██  ▄████▄ ███████ ██████  
██      ██      ██   ██ ██    ██ ██   ██ ██          ██   ██ ██   ██ ██      ██   ██ ████   ██ ██      ██      ██   ██ 
██      ██      ███████ ██    ██ ██   ██ █████       ██████  ███████ ██      ███████ ██ ██  ██ ██      █████   ██████  
██      ██      ██   ██ ██    ██ ██   ██ ██          ██   ██ ██   ██ ██      ██   ██ ██  ██ ██ ██      ██      ██   ██ 
 ▀████▀ ███████ ██   ██  ██████  ██████  ███████     ██████  ██   ██ ███████ ██   ██ ██   ████  ▀████▀ ███████ ██   ██ 
══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
"""

    _console.print(banner, style="bold green")

    if provider_manager:
        # Display provider information
        providers_text = ""
        healthy_count = len(provider_manager.get_healthy_providers())
        total_count = len(provider_manager.providers)
        for i, provider in enumerate(provider_manager.providers):
            status_icon = "✓" if provider.is_healthy(provider_manager.get_failure_cooldown()) else "✗"
            provider_line = f"\n   [{status_icon}] {provider.name} ({provider.type.value}): {provider.base_url}"
            providers_text += provider_line
        
        # Convert absolute log file path to relative for display
        log_file_display = "Disabled"
        if settings.log_file_path:
            try:
                project_root = Path(__file__).parent.parent
                log_path = Path(settings.log_file_path)
                log_file_display = str(log_path.relative_to(project_root))
            except ValueError:
                # If path is not relative to project root, show basename
                log_file_display = Path(settings.log_file_path).name
        
        reload_enabled = global_config.get('settings', {}).get('reload', False)
        reload_status = "enabled" if reload_enabled else "disabled"
        reload_color = "green" if reload_enabled else "dim"
        
        config_details_text = Text.assemble(
            ("   Version       : ", "default"),
            (f"v{settings.app_version} (Refactored)", "bold cyan"),
            ("\n   Providers     : ", "default"),
            (f"{healthy_count}/{total_count} healthy", "bold green" if healthy_count > 0 else "bold red"),
            (providers_text, "default"),
            ("\n   Log Level     : ", "default"),
            (settings.log_level.upper(), "yellow"),
            ("\n   Log File      : ", "default"),
            (log_file_display, "dim"),
            ("\n   Auto Reload   : ", "default"),
            (reload_status, reload_color),
            ("\n   Listening on  : ", "default"),
            (f"http://{settings.host}:{settings.port}", "default")
        )
        title = "Claude Code Provider Balancer Configuration (Modular)"
    else:
        reload_enabled = global_config.get('settings', {}).get('reload', False)
        reload_status = "enabled" if reload_enabled else "disabled"
        reload_color = "green" if reload_enabled else "dim"
        
        config_details_text = Text.assemble(
            ("   Version       : ", "default"),
            (f"v{settings.app_version} (Refactored)", "bold cyan"),
            ("\n   Status        : ", "default"),
            ("Provider manager failed to initialize", "bold red"),
            ("\n   Log Level     : ", "default"),
            (settings.log_level.upper(), "yellow"),
            ("\n   Auto Reload   : ", "default"),
            (reload_status, reload_color),
            ("\n   Listening on  : ", "default"),
            (f"http://{settings.host}:{settings.port}", "default"),
        )
        title = "Claude Code Provider Balancer Configuration (ERROR)"

    _console.print(
        Panel(
            config_details_text,
            title=title,
            border_style="blue",
            expand=False,
        )
    )
    _console.print(Rule("Starting uvicorn server ...", style="dim blue"))


if __name__ == "__main__":
    # Display startup banner
    _display_startup_banner()
    
    # Get reload setting from global config
    reload_enabled = global_config.get('settings', {}).get('reload', False)
    reload_includes = global_config.get('settings', {}).get('reload_includes', ["config.yaml", "*.py"]) if reload_enabled else None
    
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=reload_enabled,
        reload_includes=reload_includes,
        log_config=log_config,
    )