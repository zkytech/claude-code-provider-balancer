#!/usr/bin/env python3
"""
Test mock server runner.
Starts a standalone mock provider server for testing.
"""

import sys
import os
from pathlib import Path

# Add src to Python path
current_dir = Path(__file__).parent
src_dir = current_dir.parent / "src"
sys.path.insert(0, str(src_dir))

import uvicorn
import fastapi
from pathlib import Path
from routers.mock_providers import create_all_mock_provider_routes
from framework.unified_mock import create_unified_mock_router

def create_test_mock_app():
    """Create test mock provider application."""
    app = fastapi.FastAPI(
        title="Test Mock Provider Server",
        version="0.1.0",
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
    
    # Check for reload flag
    enable_reload = "--reload" in sys.argv or "--auto-reload" in sys.argv
    
    app = create_test_mock_app()
    
    print("🚀 Starting test mock provider server on localhost:8998")
    if enable_reload:
        print("🔄 Auto-reload enabled - server will restart on file changes")
    print("📊 Health check: http://127.0.0.1:8998/health")
    print("🧪 Test context: http://127.0.0.1:8998/mock-test-context")
    print("⚙️  Set context: POST http://127.0.0.1:8998/mock-set-context")
    print("-" * 60)
    print_available_endpoints(app)
    
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
        host="127.0.0.1",
        port=8998,
        log_level="info",
        reload=enable_reload,
        reload_dirs=reload_dirs,
        factory=True if enable_reload else False
    )