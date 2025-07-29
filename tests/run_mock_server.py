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
from pathlib import Path
from framework.unified_mock import create_unified_mock_router
from utils import init_logger

def setup_test_logging():
    """Setup basic logging for mock server"""
    # Initialize logger
    init_logger("test-mock-provider")
    
    # Setup basic logging level
    import logging
    logging.getLogger().setLevel(logging.INFO)

def create_test_mock_app():
    """Create test mock provider application."""
    # Setup logging
    setup_test_logging()
    
    app = fastapi.FastAPI(
        title="Test Mock Provider Server",
        version="0.1.0",
        description="Mock provider endpoints for simplified testing framework",
    )
    
    # Register the unified mock router (for simplified tests)
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
    
    # Default server settings
    host = "127.0.0.1"
    port = 8998
    log_level = "info"
    
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
    print("-" * 60)
    print_available_endpoints(app, host, port)
    
    # Configure reload directories if reload is enabled
    reload_dirs = None
    if enable_reload:
        current_dir = Path(__file__).parent
        reload_dirs = [
            str(current_dir / "framework"),
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