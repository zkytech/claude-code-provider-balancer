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

from main import AppComponents, create_app
from utils import LogRecord, LogEvent, debug
from routers.messages.handlers import MessageHandler


def create_test_app(config_path: str) -> fastapi.FastAPI:
    """
    Create a test application instance with isolated configuration.
    
    This creates a completely separate instance of the application
    that doesn't interfere with any running production instance.
    
    Args:
        config_path: Path to test configuration file
        
    Returns:
        FastAPI application instance configured for testing
    """
    # Force reset of global components for test isolation
    import main
    main._app_components = None
    
    # Create test app with isolated components
    test_app = create_app(config_path)
    
    # Modify metadata to indicate test environment
    test_app.title = f"{test_app.title} (Test Environment)"
    test_app.description = f"{test_app.description} - Test Instance"
    
    # Add test-specific middleware for request tracking
    @test_app.middleware("http")
    async def test_tracking_middleware(request: Request, call_next):
        """Track test requests with special logging."""
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        
        debug(LogRecord(
            event=LogEvent.HTTP_REQUEST.value,
            message=f"TEST: {request.method} {request.url.path}",
            data={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time": round(process_time, 3),
                "test_environment": True,
                "client_host": request.client.host if request.client else "unknown",
            },
        ))
        
        return response
    
    return test_app


def create_isolated_test_app(config_path: str, test_name: str = "default") -> fastapi.FastAPI:
    """
    Create a fully isolated test app with custom test identification.
    
    This is useful when running multiple test instances simultaneously
    or when you need complete isolation between test runs.
    
    Args:
        config_path: Path to test configuration file
        test_name: Identifier for this test instance
        
    Returns:
        FastAPI application instance with test isolation
    """
    # Create completely isolated components
    test_components = AppComponents(config_path)
    test_components.initialize()
    
    # Create FastAPI app with isolated components
    test_app = fastapi.FastAPI(
        title=f"Claude Code Provider Balancer (Test: {test_name})",
        version=test_components.settings.app_version,
        description=f"Test instance '{test_name}' of Claude Code Provider Balancer",
    )
    
    # Import routers
    from routers.messages import create_messages_router
    from routers.oauth import create_oauth_router
    from routers.health import create_health_router
    from routers.management import create_management_router
    
    # Register routers with isolated components
    test_app.include_router(create_messages_router(test_components.provider_manager, test_components.settings))
    test_app.include_router(create_oauth_router(test_components.provider_manager))
    test_app.include_router(create_health_router(test_components.provider_manager, test_components.settings.app_name, test_components.settings.app_version))
    test_app.include_router(create_management_router(test_components.provider_manager))
    
    # Add test-specific exception handlers
    @test_app.exception_handler(ValidationError)
    async def test_validation_error_handler(request: Request, exc: ValidationError):
        import uuid
        handler = MessageHandler(test_components.provider_manager, test_components.settings)
        request_id = str(uuid.uuid4())
        return await handler.log_and_return_error_response(request, exc, request_id, 400)
    
    @test_app.exception_handler(json.JSONDecodeError)
    async def test_json_error_handler(request: Request, exc: json.JSONDecodeError):
        import uuid
        handler = MessageHandler(test_components.provider_manager, test_components.settings)
        request_id = str(uuid.uuid4())
        return await handler.log_and_return_error_response(request, exc, request_id, 400)
    
    @test_app.exception_handler(Exception)
    async def test_generic_error_handler(request: Request, exc: Exception):
        import uuid
        handler = MessageHandler(test_components.provider_manager, test_components.settings)
        request_id = str(uuid.uuid4())
        return await handler.log_and_return_error_response(request, exc, request_id, 500)
    
    # Add test identification middleware
    @test_app.middleware("http")
    async def test_isolation_middleware(request: Request, call_next):
        """Add test instance identification to all requests."""
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        
        # Add test headers
        response.headers["X-Test-Instance"] = test_name
        response.headers["X-Test-Environment"] = "isolated"
        
        debug(LogRecord(
            event=LogEvent.HTTP_REQUEST.value,
            message=f"ISOLATED_TEST[{test_name}]: {request.method} {request.url.path}",
            data={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time": round(process_time, 3),
                "test_instance": test_name,
                "test_environment": "isolated",
            },
        ))
        
        return response
    
    return test_app


def reset_test_environment():
    """
    Reset the global test environment state.
    
    Call this between test runs to ensure clean state.
    """
    import main
    main._app_components = None
    
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