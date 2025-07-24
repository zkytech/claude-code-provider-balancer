"""
API layer modules.

This package contains FastAPI endpoint handlers and middleware:
- REST API endpoints
- Request/response processing
- Middleware components
"""

from .endpoints import create_app

__all__ = ["create_app"]