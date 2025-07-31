"""
Test Application Factory

Creates isolated test instances of the Claude Code Provider Balancer
with proper test environment configuration.
"""

import json
import os
import sys
import time
from pathlib import Path

import fastapi
from fastapi import Request
from pydantic import ValidationError

# Add src to path for imports
src_dir = Path(__file__).parent.parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from main import create_app
from utils import LogRecord, LogEvent, debug
from routers.messages.handlers import MessageHandler


def create_test_app(config_path: str, test_name: str = None) -> fastapi.FastAPI:
    """
    Create a test application instance with isolated configuration.
    
    This creates a completely separate instance of the application
    that doesn't interfere with any running production instance.
    
    Args:
        config_path: Path to test configuration file
        test_name: Optional identifier for this test instance (for isolation)
        
    Returns:
        FastAPI application instance configured for testing
    """
    # Create test app with isolated configuration
    test_app = create_app(config_path, environment="test")
    
    # Modify metadata if test_name is provided
    if test_name:
        test_app.title = f"Claude Code Provider Balancer (Test: {test_name})"
        test_app.description = f"Test instance '{test_name}' of Claude Code Provider Balancer"
    
    # Add test-specific middleware for request tracking
    @test_app.middleware("http")
    async def test_tracking_middleware(request: Request, call_next):
        """Track test requests with special logging."""
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        
        # Add test headers if test_name is provided
        if test_name:
            response.headers["X-Test-Instance"] = test_name
            response.headers["X-Test-Environment"] = "isolated"
        
        # Choose log message prefix based on test_name
        message_prefix = f"ISOLATED_TEST[{test_name}]" if test_name else "TEST"
        
        debug(LogRecord(
            event=LogEvent.HTTP_REQUEST.value,
            message=f"{message_prefix}: {request.method} {request.url.path}",
            data={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time": round(process_time, 3),
                "test_environment": True,
                "test_instance": test_name,
                "client_host": request.client.host if request.client else "unknown",
            },
        ))
        
        return response
    
    return test_app

def reset_test_environment():
    """
    Reset the global test environment state.
    
    Call this between test runs to ensure clean state.
    Note: With the new isolated approach, this is less critical
    since each create_app() call creates independent components.
    """
    # Clear any cached modules that might hold state
    import sys
    modules_to_reload = [
        name for name in sys.modules.keys() 
        if name.startswith(('core.', 'oauth', 'caching.', 'routers.'))
    ]
    
    for module_name in modules_to_reload:
        if hasattr(sys.modules[module_name], '__dict__'):
            # Reset module-level variables that might hold state
            module_dict = sys.modules[module_name].__dict__
            for key, value in list(module_dict.items()):
                if key.startswith('_') and not key.startswith('__'):
                    # Reset private module variables
                    if not callable(value) and not isinstance(value, type):
                        module_dict[key] = None