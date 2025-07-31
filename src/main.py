"""
Claude Code Provider Balancer - Main Application Entry Point

Modular FastAPI application with clear separation of concerns:
- Clean environment isolation (production vs test)
- Single initialization flow
- Robust error handling
"""

import argparse
import json
import os
import sys
import time
import yaml
from contextlib import asynccontextmanager
from logging.config import dictConfig
from pathlib import Path

import fastapi
import uvicorn
from dotenv import load_dotenv
from fastapi import Request
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

# Configure path for imports
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

# Rich console for startup display
_console = Console()

# ===== CONFIGURATION MANAGEMENT =====

class AppSettings:
    """Application settings with environment-specific defaults."""
    
    def __init__(self, config_path: str = "config.yaml"):
        # Default values
        self.log_level: str = "INFO"
        self.log_file_path: str = ""
        self.log_color: bool = True
        self.host: str = "127.0.0.1"
        self.port: int = 9090
        self.app_name: str = "Claude Code Provider Balancer"
        self.app_version: str = "0.1.6"
        
        # Load from config file
        self.load_from_config(config_path)
    
    def load_from_config(self, config_path: str):
        """Load settings from configuration file."""
        # Resolve absolute path
        if not os.path.isabs(config_path):
            project_root = Path(__file__).parent.parent
            config_path = project_root / config_path
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # Update settings from config
            settings_config = config.get('settings', {})
            for key, value in settings_config.items():
                if hasattr(self, key):
                    # Special handling for log file path
                    if key == "log_file_path" and value and not os.path.isabs(value):
                        project_root = Path(__file__).parent.parent
                        value = str(project_root / value)
                    setattr(self, key, value)
                    
        except Exception as e:
            print(f"Warning: Failed to load settings from {config_path}: {e}")
            print("Using default settings.")

def load_config(config_path: str = "config.yaml") -> dict:
    """Load full configuration from file."""
    if not os.path.isabs(config_path):
        project_root = Path(__file__).parent.parent
        config_path = project_root / config_path
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Failed to load config file: {e}")
        return {}

# ===== APPLICATION COMPONENTS =====

class AppComponents:
    """Container for application-wide components."""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.settings = AppSettings(config_path)
        self.config = load_config(config_path)
        self.provider_manager = None
        self._initialized = False
    
    def initialize(self):
        """Initialize all components."""
        if self._initialized:
            return
        
        # Initialize logging
        init_logger(self.settings.app_name)
        self._setup_logging()
        
        # Create provider manager
        try:
            self.provider_manager = ProviderManager(self.config_path)
            
            # Initialize OAuth manager
            self._initialize_oauth()
            
            # Set provider manager reference for deduplication
            from caching.deduplication import set_provider_manager
            set_provider_manager(self.provider_manager)
            
            self._initialized = True
            
        except Exception as e:
            print(f"FATAL ERROR: Failed to initialize components: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    def _setup_logging(self):
        """Setup logging configuration."""
        log_config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "colored_console": {"()": ColoredConsoleFormatter},
                "json": {"()": JSONFormatter},
                "uvicorn_access": {"()": "utils.logging.formatters.UvicornAccessFormatter"},
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": self.settings.log_level,
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
                self.settings.app_name: {
                    "level": self.settings.log_level,
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
        
        # Add file handler if configured
        if self.settings.log_file_path:
            log_config["handlers"]["file"] = {
                "class": "logging.FileHandler",
                "level": self.settings.log_level,
                "formatter": "json",
                "filename": self.settings.log_file_path,
                "mode": "a",
                "encoding": "utf-8",
            }
            log_config["loggers"][self.settings.app_name]["handlers"].append("file")
        
        dictConfig(log_config)
        self.log_config = log_config
    
    def _initialize_oauth(self):
        """Initialize OAuth manager."""
        try:
            # Check if OAuth manager already has tokens
            from oauth import oauth_manager
            had_tokens = oauth_manager and oauth_manager.token_credentials
            
            init_oauth_manager(self.provider_manager.settings)
            
            # Only log if actually initialized
            if not had_tokens:
                info(LogRecord(
                    event=LogEvent.OAUTH_MANAGER_READY.value,
                    message="OAuth manager initialization completed successfully"
                ))
                
        except Exception as e:
            from utils import error
            error(LogRecord(
                event=LogEvent.OAUTH_MANAGER_INIT_FAILED.value,
                message=f"Failed to initialize OAuth manager: {e}"
            ))

# Global components instance
_app_components = None
_app_components_lock = None

def get_app_components(config_path: str = "config.yaml") -> AppComponents:
    """Get or create application components with thread-safe singleton pattern."""
    global _app_components, _app_components_lock
    
    # Initialize lock if needed
    if _app_components_lock is None:
        import threading
        _app_components_lock = threading.Lock()
    
    # Double-checked locking pattern
    if _app_components is None:
        with _app_components_lock:
            if _app_components is None:
                _app_components = AppComponents(config_path)
                _app_components.initialize()
    
    return _app_components

# ===== FASTAPI APPLICATION =====

@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    """FastAPI lifespan event handler."""
    # Startup
    info(LogRecord(
        event=LogEvent.FASTAPI_STARTUP_COMPLETE.value,
        message="FastAPI application startup complete"
    ))
    
    # Start OAuth auto-refresh
    try:
        components = get_app_components()
        auto_refresh = components.provider_manager.oauth_auto_refresh_enabled if components.provider_manager else True
        await start_oauth_auto_refresh(auto_refresh)
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

def create_app(config_path: str = "config.yaml") -> fastapi.FastAPI:
    """Create FastAPI application."""
    # Get components
    components = get_app_components(config_path)
    
    # Create FastAPI app
    app = fastapi.FastAPI(
        title=components.settings.app_name,
        version=components.settings.app_version,
        description="Intelligent load balancer and failover proxy for Claude Code providers",
        lifespan=lifespan,
    )
    
    # Register routers
    app.include_router(create_messages_router(components.provider_manager, components.settings))
    app.include_router(create_oauth_router(components.provider_manager))
    app.include_router(create_health_router(components.provider_manager, components.settings.app_name, components.settings.app_version))
    app.include_router(create_management_router(components.provider_manager))
    
    # Exception handlers
    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError):
        import uuid
        from routers.messages.handlers import MessageHandler
        handler = MessageHandler(components.provider_manager, components.settings)
        request_id = str(uuid.uuid4())
        return await handler.log_and_return_error_response(request, exc, request_id, 400)
    
    @app.exception_handler(json.JSONDecodeError)
    async def json_error_handler(request: Request, exc: json.JSONDecodeError):
        import uuid
        from routers.messages.handlers import MessageHandler
        handler = MessageHandler(components.provider_manager, components.settings)
        request_id = str(uuid.uuid4())
        return await handler.log_and_return_error_response(request, exc, request_id, 400)
    
    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        import uuid
        from routers.messages.handlers import MessageHandler
        handler = MessageHandler(components.provider_manager, components.settings)
        request_id = str(uuid.uuid4())
        return await handler.log_and_return_error_response(request, exc, request_id, 500)
    
    # Request logging middleware
    @app.middleware("http")
    async def logging_middleware(request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        
        from utils import debug
        debug(LogRecord(
            event=LogEvent.HTTP_REQUEST.value,
            message=f"{request.method} {request.url.path}",
            data={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time": round(process_time, 3),
            },
        ))
        
        return response
    
    return app


# ===== STARTUP BANNER =====

def display_startup_banner(components: AppComponents):
    """Display startup banner with configuration info."""
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
    
    try:
        # Provider information
        providers_config = components.config.get('providers', [])
        providers_text = ""
        enabled_count = 0
        total_count = 0
        
        for provider_config in providers_config:
            total_count += 1
            is_enabled = provider_config.get('enabled', True)
            if is_enabled:
                enabled_count += 1
            
            status_icon = "✓" if is_enabled else "✗"
            provider_type = provider_config.get('type', 'unknown')
            provider_name = provider_config.get('name', 'Unknown')
            provider_url = provider_config.get('base_url', 'Unknown')
            provider_line = f"\n   [{status_icon}] {provider_name} ({provider_type}): {provider_url}"
            providers_text += provider_line
        
        # Log file display
        log_file_display = "Disabled"
        if components.settings.log_file_path:
            try:
                project_root = Path(__file__).parent.parent
                log_path = Path(components.settings.log_file_path)
                log_file_display = str(log_path.relative_to(project_root))
            except ValueError:
                log_file_display = Path(components.settings.log_file_path).name
        
        # Reload configuration
        reload_enabled = components.config.get('settings', {}).get('reload', False)
        reload_status = "enabled" if reload_enabled else "disabled"
        reload_color = "green" if reload_enabled else "dim"
        
        config_text = Text.assemble(
            ("   Version       : ", "default"),
            (f"v{components.settings.app_version}", "bold cyan"),
            ("\n   Environment   : ", "default"),
            ("Production", "bold green"),
            ("\n   Providers     : ", "default"),
            (f"{enabled_count}/{total_count} enabled", "bold green" if enabled_count > 0 else "bold red"),
            (providers_text, "default"),
            ("\n   Log Level     : ", "default"),
            (components.settings.log_level.upper(), "yellow"),
            ("\n   Log File      : ", "default"),
            (log_file_display, "dim"),
            ("\n   Auto Reload   : ", "default"),
            (reload_status, reload_color),
            ("\n   Listening on  : ", "default"),
            (f"http://{components.settings.host}:{components.settings.port}", "default")
        )
        
    except Exception as e:
        config_text = Text.assemble(
            ("   Version       : ", "default"),
            (f"v{components.settings.app_version}", "bold cyan"),
            ("\n   Status        : ", "default"),
            (f"Configuration error: {e}", "bold red"),
            ("\n   Listening on  : ", "default"),
            (f"http://{components.settings.host}:{components.settings.port}", "default"),
        )
    
    _console.print(Panel(
        config_text,
        title="Claude Code Provider Balancer Configuration",
        border_style="blue",
        expand=False,
    ))
    _console.print(Rule("Starting uvicorn server ...", style="dim blue"))

# ===== COMMAND LINE INTERFACE =====

def parse_args():
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
    parser.add_argument(
        '--env',
        type=str,
        choices=['production', 'test'],
        default='production',
        help='Environment mode (default: production)'
    )
    return parser.parse_args()

# ===== APPLICATION ENTRY POINT =====

# Create app instance for uvicorn (simple and direct)
app = create_app()

def main():
    """Main entry point."""
    args = parse_args()
    
    # Get components with config overrides
    components = get_app_components(args.config)
    
    # Apply command line overrides
    if args.port:
        components.settings.port = args.port
    if args.host:
        components.settings.host = args.host
    
    # Display startup banner
    display_startup_banner(components)
    
    # Get reload settings
    reload_enabled = components.config.get('settings', {}).get('reload', False)
    reload_includes = components.config.get('settings', {}).get('reload_includes', ["config.yaml", "*.py"]) if reload_enabled else None
    
    # Start server
    uvicorn.run(
        "main:app",
        host=components.settings.host,
        port=components.settings.port,
        reload=reload_enabled,
        reload_includes=reload_includes,
        log_config=components.log_config,
    )

if __name__ == "__main__":
    main()