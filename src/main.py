"""
Claude Code Provider Balancer - Main Application Entry Point

Modular FastAPI application with separated concerns:
- Routers: API endpoint definitions
- Handlers: Business logic
- Core: Provider management, streaming, etc.
"""

import argparse
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
    LogRecord, LogEvent, ColoredConsoleFormatter, JSONFormatter,
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


def _parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Claude Code Provider Balancer')
    parser.add_argument(
        '--config', 
        type=str, 
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )
    parser.add_argument(
        '--port',
        type=int,
        help='Port to run the server on (overrides config file)'
    )
    parser.add_argument(
        '--host',
        type=str,
        help='Host to bind the server to (overrides config file)'
    )
    return parser.parse_args()


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
            event_name = LogEvent.OAUTH_MANAGER_REINITIALIZED.value if is_reload else LogEvent.OAUTH_MANAGER_READY.value
            message = "OAuth manager re-initialized after config reload" if is_reload else "OAuth manager initialization completed successfully"
            
            info(LogRecord(
                event=event_name,
                message=message
            ))
        
        return True
    except Exception as e:
        event_name = LogEvent.OAUTH_MANAGER_REINIT_FAILED.value if is_reload else LogEvent.OAUTH_MANAGER_INIT_FAILED.value
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


# Global variables - will be initialized in main
args = None
provider_manager = None
settings = None
global_config = {}
log_config = {}

def _initialize_main_components():
    """Initialize main application components when running as main script."""
    global args, provider_manager, settings, global_config, log_config
    
    # Parse command line arguments
    args = _parse_args()

    # Initialize provider manager and settings
    try:
        provider_manager = ProviderManager()
        settings = Settings()
        
        # Load settings from provider config file
        settings.load_from_provider_config(args.config)
        
        # Override with command line arguments if provided
        if args.port:
            settings.port = args.port
        if args.host:
            settings.host = args.host
        
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
        
        # Override with command line arguments if provided
        if args.port:
            settings.port = args.port
        if args.host:
            settings.host = args.host
        
        # Still set the provider manager reference (even if None)
        from caching.deduplication import set_provider_manager
        set_provider_manager(provider_manager)

    # Global config instance
    global_config = load_global_config(args.config)

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
        event=LogEvent.FASTAPI_STARTUP_COMPLETE.value,
        message="FastAPI application startup complete"
    ))
    info(LogRecord(
        event=LogEvent.OAUTH_MANAGER_READY.value,
        message="OAuth manager ready for Claude Code Official authentication"
    ))
    
    # Start auto-refresh for any loaded OAuth tokens
    try:
        # Get auto-refresh setting from provider manager
        auto_refresh_enabled = provider_manager.oauth_auto_refresh_enabled if provider_manager else True
        await start_oauth_auto_refresh(auto_refresh_enabled)
    except Exception as e:
        warning(LogRecord(
            event=LogEvent.OAUTH_AUTO_REFRESH_START_FAILED.value,
            message=f"Failed to start OAuth auto-refresh: {e}"
        ))
    
    yield
    
    # Shutdown
    info(LogRecord(
        event=LogEvent.FASTAPI_SHUTDOWN.value,
        message="FastAPI application shutting down"
    ))


# App will be created in main function
app = None

def _create_main_app():
    """Create the main FastAPI application."""
    global app
    
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
        from routers.messages.handlers import MessageHandler
        handler = MessageHandler(provider_manager, settings)
        request_id = str(uuid.uuid4())
        return await handler.log_and_return_error_response(request, exc, request_id, 400)

    @app.exception_handler(json.JSONDecodeError)
    async def json_decode_error_handler(request: Request, exc: json.JSONDecodeError):
        """Handle JSON decode errors."""
        import uuid
        from routers.messages.handlers import MessageHandler
        handler = MessageHandler(provider_manager, settings)
        request_id = str(uuid.uuid4())
        return await handler.log_and_return_error_response(request, exc, request_id, 400)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        """Handle generic exceptions."""
        import uuid
        from routers.messages.handlers import MessageHandler
        handler = MessageHandler(provider_manager, settings)
        request_id = str(uuid.uuid4())
        return await handler.log_and_return_error_response(request, exc, request_id, 500)

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
                event=LogEvent.HTTP_REQUEST.value,
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
            (f"v{settings.app_version}", "bold cyan"),
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
            (f"v{settings.app_version}", "bold cyan"),
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


def create_test_app(config_path: str):
    """Create a test application instance with specific configuration."""
    # Import required modules
    from core.provider_manager import ProviderManager
    from oauth import init_oauth_manager
    from caching.deduplication import set_provider_manager
    
    # Create test settings and load configuration first
    test_settings = Settings()
    test_settings.load_from_provider_config(config_path)
    
    # Initialize logging for test app
    init_logger(test_settings.app_name)
    
    # Setup test logging configuration
    import logging
    from logging.config import dictConfig
    
    # Create a custom formatter class for test server logs with prefix
    class TestServerFormatter(ColoredConsoleFormatter):
        def format(self, record):
            formatted = super().format(record)
            return f"{formatted}"
    
    test_log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "colored_console": {
                "()": ColoredConsoleFormatter,
            },
            "prefixed_console": {
                "()": TestServerFormatter,
            },
            "json": {
                "()": JSONFormatter,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": test_settings.log_level,
                "formatter": "colored_console",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            test_settings.app_name: {
                "level": test_settings.log_level,
                "handlers": ["console"],
                "propagate": False,
            },
        },
    }
    
    # Always add file handler for test logs to separate them from test output
    import os
    test_log_dir = "logs"
    os.makedirs(test_log_dir, exist_ok=True)
    test_log_file = os.path.join(test_log_dir, "test-logs.jsonl")
    
    test_log_config["handlers"]["file"] = {
        "class": "logging.FileHandler",
        "level": test_settings.log_level,
        "formatter": "json",
        "filename": test_log_file,
        "mode": "a",
        "encoding": "utf-8",
    }
    test_log_config["loggers"][test_settings.app_name]["handlers"] = ["file"]  # Only file handler, no console
    
    # Add a separate console handler with prefix for balancer logs
    test_log_config["handlers"]["prefixed_console"] = {
        "class": "logging.StreamHandler",
        "level": "INFO",  # Only show INFO and above on console
        "formatter": "prefixed_console",
        "stream": "ext://sys.stderr",  # Use stderr to separate from pytest output
    }
    
    # Add the prefixed console handler for important logs
    test_log_config["loggers"][test_settings.app_name]["handlers"].append("prefixed_console")
    
    dictConfig(test_log_config)
    
    # Create test provider manager with the test config file path
    test_provider_manager = ProviderManager(config_path)
    
    # Initialize OAuth manager with test config settings
    try:
        init_oauth_manager(test_provider_manager.settings)
    except Exception as e:
        # OAuth initialization is optional for tests
        pass
    
    # Set provider manager reference for deduplication module
    set_provider_manager(test_provider_manager)
    
    # Create test FastAPI app
    test_app = fastapi.FastAPI(
        title=f"{test_settings.app_name} (Test)",
        version=test_settings.app_version,
        description="Test instance of Claude Code Provider Balancer",
        # Don't use lifespan for test app to avoid conflicts
    )
    
    # Register routers with test instances
    test_app.include_router(create_messages_router(test_provider_manager, test_settings))
    test_app.include_router(create_oauth_router(test_provider_manager))
    test_app.include_router(create_health_router(test_provider_manager, test_settings.app_name, test_settings.app_version))
    test_app.include_router(create_management_router(test_provider_manager))
    
    # Add basic exception handlers
    @test_app.exception_handler(ValidationError)
    async def test_pydantic_validation_error_handler(request: Request, exc: ValidationError):
        import uuid
        from routers.messages.handlers import MessageHandler
        handler = MessageHandler(test_provider_manager, test_settings)
        request_id = str(uuid.uuid4())
        return await handler.log_and_return_error_response(request, exc, request_id, 400)
    
    @test_app.exception_handler(json.JSONDecodeError)
    async def test_json_decode_error_handler(request: Request, exc: json.JSONDecodeError):
        import uuid
        from routers.messages.handlers import MessageHandler
        handler = MessageHandler(test_provider_manager, test_settings)
        request_id = str(uuid.uuid4())
        return await handler.log_and_return_error_response(request, exc, request_id, 400)
    
    @test_app.exception_handler(Exception)
    async def test_generic_exception_handler(request: Request, exc: Exception):
        import uuid
        from routers.messages.handlers import MessageHandler
        handler = MessageHandler(test_provider_manager, test_settings)
        request_id = str(uuid.uuid4())
        return await handler.log_and_return_error_response(request, exc, request_id, 500)
    
    # Add logging middleware for test app
    @test_app.middleware("http")
    async def test_logging_middleware(request: Request, call_next):
        """Log all requests and responses in test environment."""
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        
        from utils import debug
        debug(
            LogRecord(
                event=LogEvent.HTTP_REQUEST.value,
                message=f"TEST: {request.method} {request.url.path}",
                data={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "process_time": round(process_time, 3),
                    "test_environment": True,
                },
            )
        )
        
        return response
    
    return test_app


if __name__ == "__main__":
    # Initialize all main components
    _initialize_main_components()
    
    # Create the main app
    _create_main_app()
    
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