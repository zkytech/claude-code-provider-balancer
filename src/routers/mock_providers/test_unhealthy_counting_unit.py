"""
Mock providers specifically for test_unhealthy_counting_unit.py
Handles unhealthy provider counting testing scenarios.
"""

import json
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse


def create_test_unhealthy_counting_unit_routes():
    """Create mock provider routes for test_unhealthy_counting_unit.py"""
    router = APIRouter()

    @router.post("/anthropic-unhealthy-test-single/v1/messages")
    async def mock_anthropic_single_error_test(request: Request):
        """Mock provider that returns connection error - for testing single error scenarios."""
        # Always return connection error for testing
        return JSONResponse(
            status_code=502,
            content={
                "type": "error",
                "error": {
                    "type": "bad_gateway",
                    "message": "Connection failed - simulated single error"
                }
            }
        )

    @router.post("/anthropic-unhealthy-test-multiple/v1/messages")
    async def mock_anthropic_multiple_error_test(request: Request):
        """Mock provider that returns connection error - for testing multiple error scenarios."""
        # Always return connection error for testing
        return JSONResponse(
            status_code=502,
            content={
                "type": "error",
                "error": {
                    "type": "bad_gateway",
                    "message": "Connection failed - simulated multiple error"
                }
            }
        )

    @router.post("/anthropic-unhealthy-test-reset/v1/messages")
    async def mock_anthropic_error_reset_test(request: Request):
        """Mock provider that returns connection error - for testing error reset scenarios."""
        # Always return connection error for testing
        return JSONResponse(
            status_code=502,
            content={
                "type": "error",
                "error": {
                    "type": "bad_gateway",
                    "message": "Intermittent failure - simulated error"
                }
            }
        )

    @router.post("/anthropic-unhealthy-test-always-fail/v1/messages")
    async def mock_anthropic_always_fail_test(request: Request):
        """Mock provider that always fails - for testing continuous errors."""
        # Always return connection error
        return JSONResponse(
            status_code=502,
            content={
                "type": "error",
                "error": {
                    "type": "bad_gateway",
                    "message": "Always fails - simulated continuous error"
                }
            }
        )

    return router