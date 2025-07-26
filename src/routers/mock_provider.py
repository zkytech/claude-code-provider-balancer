"""
Mock provider router for testing SSE error scenarios.
Simulates the exact error response that causes client issues.
"""

import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse


def create_mock_provider_router() -> APIRouter:
    """Create mock provider router for testing."""
    router = APIRouter(prefix="/mock", tags=["Mock Provider"])

    @router.post("/sse_error/v1/messages")
    async def mock_sse_error():
        """Mock endpoint that returns SSE error like GAC overloaded_error."""
        
        async def generate_sse_error():
            """Generate the exact SSE error that causes client issues."""
            error_data = {
                "type": "error",
                "error": {
                    "details": None,
                    "type": "overloaded_error",
                    "message": "Overloaded"
                }
            }
            yield f'event: error\ndata: {json.dumps(error_data)}\n\n'
        
        return StreamingResponse(
            generate_sse_error(),
            media_type="text/event-stream"
        )

    return router