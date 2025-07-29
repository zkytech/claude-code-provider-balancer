#!/usr/bin/env python3
"""
Test mock server runner.
Starts a standalone mock provider server for testing.
"""

import sys
import os
import logging
from pathlib import Path

# Add src to Python path
current_dir = Path(__file__).parent
src_dir = current_dir.parent / "src"
sys.path.insert(0, str(src_dir))

import uvicorn
import fastapi
import yaml
from pathlib import Path
from routers.mock_providers import create_all_mock_provider_routes
from framework.unified_mock import create_unified_mock_router
from utils import init_logger

def load_test_config(config_path: str = "config-test.yaml") -> dict:
    """Load test configuration from YAML file"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"❌ Test config file not found: {config_path}")
        return {}
    except yaml.YAMLError as e:
        print(f"❌ Failed to parse config file: {e}")
        return {}

def setup_test_logging(config: dict):
    """Setup logging based on test configuration"""
    settings = config.get("settings", {})
    app_name = settings.get("app_name", "test-mock-provider")
    log_level = settings.get("log_level", "INFO")
    
    # Initialize logger with app name only (as per utils signature)
    init_logger(app_name)
    
    # Setup basic logging level
    import logging
    logging.getLogger().setLevel(getattr(logging, log_level.upper(), logging.INFO))

def create_test_mock_app():
    """Create test mock provider application."""
    # Load test configuration
    config_path = current_dir / "config-test.yaml"
    config = load_test_config(str(config_path))
    
    if not config:
        print("❌ Failed to load test configuration, using defaults")
        config = {"settings": {}}
    
    # Setup logging based on config
    setup_test_logging(config)
    
    settings = config.get("settings", {})
    app = fastapi.FastAPI(
        title=settings.get("app_name", "Test Mock Provider Server"),
        version=settings.get("app_version", "0.1.0"),
        description="Mock provider endpoints for testing streaming behavior",
    )
    
    # Register the traditional mock provider routes (for backward compatibility)
    app.include_router(create_all_mock_provider_routes())
    
    # Register the new unified mock router (for simplified tests)
    app.include_router(create_unified_mock_router())
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok", "service": "test-mock-provider"}
    
    @app.get("/endpoints")
    async def list_endpoints():
        """List all available endpoints dynamically."""
        routes = []
        for route in app.routes:
            if hasattr(route, 'methods') and hasattr(route, 'path'):
                for method in route.methods:
                    if method != 'HEAD':  # Skip HEAD methods
                        routes.append({
                            "method": method,
                            "path": route.path,
                            "url": f"http://127.0.0.1:8998{route.path}",
                            "name": getattr(route, 'name', None),
                            "summary": getattr(route, 'summary', None)
                        })
        
        # Sort routes for consistent output
        routes.sort(key=lambda x: (x['path'], x['method']))
        
        return {
            "total": len(routes),
            "endpoints": routes
        }
    
    return app

def print_available_endpoints(app: fastapi.FastAPI, host: str = "127.0.0.1", port: int = 8998):
    """Automatically discover and print all available endpoints."""
    print("Available endpoints:")
    
    # Collect all routes
    routes = []
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            for method in route.methods:
                if method != 'HEAD':  # Skip HEAD methods
                    routes.append((method, route.path))
    
    # Sort routes for consistent output
    routes.sort(key=lambda x: (x[1], x[0]))
    
    # Print formatted routes
    for method, path in routes:
        print(f"  - {method:4} http://{host}:{port}{path}")

if __name__ == "__main__":
    import sys
    
    # Load configuration first for proper setup
    config_path = current_dir / "config-test.yaml"
    config = load_test_config(str(config_path))
    
    if not config:
        print("❌ Failed to load test configuration, using defaults")
        config = {"settings": {}}
    
    # Get server settings from config
    settings = config.get("settings", {})
    host = settings.get("host", "127.0.0.1")
    port = settings.get("port", 8998)  # Default to 8998 if not in config
    log_level = settings.get("log_level", "INFO").lower()
    
    # Check for reload flag
    enable_reload = "--reload" in sys.argv or "--auto-reload" in sys.argv
    
    app = create_test_mock_app()
    
    print(f"🚀 Starting test mock provider server on {host}:{port}")
    if enable_reload:
        print("🔄 Auto-reload enabled - server will restart on file changes")
    print(f"📊 Health check: http://{host}:{port}/health")
    print(f"🧪 Test context: http://{host}:{port}/mock-test-context")
    print(f"⚙️  Set context: POST http://{host}:{port}/mock-set-context")
    print(f"📋 Log level: {log_level.upper()}")
    if settings.get("log_file_path"):
        print(f"📝 Log file: {settings.get('log_file_path')}")
    print("-" * 60)
    print_available_endpoints(app, host, port)
    
    # Configure reload directories if reload is enabled
    reload_dirs = None
    if enable_reload:
        current_dir = Path(__file__).parent
        reload_dirs = [
            str(current_dir / "framework"),
            str(current_dir.parent / "src" / "routers" / "mock_providers"),
            str(current_dir)  # Include the tests directory itself
        ]
        print(f"👀 Monitoring directories: {reload_dirs}")
    
    uvicorn.run(
        "run_mock_server:create_test_mock_app" if enable_reload else app,
        host=host,
        port=port,
        log_level=log_level,
        reload=enable_reload,
        reload_dirs=reload_dirs,
        factory=True if enable_reload else False
    )