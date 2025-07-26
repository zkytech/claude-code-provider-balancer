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
from routers.mock_provider import create_mock_provider_router

def create_test_mock_app():
    """Create test mock provider application."""
    app = fastapi.FastAPI(
        title="Test Mock Provider Server",
        version="0.1.0",
        description="Mock provider endpoints for testing streaming behavior",
    )
    
    # Register only the mock provider router
    app.include_router(create_mock_provider_router())
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok", "service": "test-mock-provider"}
    
    return app

if __name__ == "__main__":
    app = create_test_mock_app()
    
    print("Starting test mock provider server on localhost:8998")
    print("Available endpoints:")
    print("  - POST http://localhost:8998/test-providers/anthropic/v1/messages")
    print("  - POST http://localhost:8998/test-providers/anthropic-sse-error/v1/messages")  
    print("  - POST http://localhost:8998/test-providers/openai/v1/chat/completions")
    print("  - GET  http://localhost:8998/health")
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8998,
        log_level="info"
    )