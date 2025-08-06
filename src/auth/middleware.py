"""
Authentication middleware for FastAPI.
"""

import uuid
from typing import Callable
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from .auth_manager import AuthManager


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for API authentication."""
    
    def __init__(self, app: Callable, auth_manager: AuthManager):
        super().__init__(app)
        self.auth_manager = auth_manager
    
    async def dispatch(self, request: Request, call_next):
        """Process the request with authentication."""
        request_id = str(uuid.uuid4())
        
        try:
            # Perform authentication using the same approach as upstream providers
            # Support both x-api-key (Anthropic style) and Authorization Bearer (OpenAI style)
            api_key = request.headers.get("x-api-key")
            authorization = request.headers.get("authorization")
            path = request.url.path
            
            self.auth_manager.authenticate_request(api_key, authorization, path, request_id)
            
            # Authentication successful, continue to next middleware/endpoint
            response = await call_next(request)
            return response
            
        except Exception as e:
            # Authentication failed, return 401 error
            return JSONResponse(
                content={
                    "error": {
                        "type": "authentication_error",
                        "message": str(e),
                        "code": "AUTH_FAILED"
                    }
                },
                status_code=401
            )