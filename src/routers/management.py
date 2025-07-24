"""
Management API routes for Claude Code Provider Balancer.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from caching import cleanup_stuck_requests


def create_management_router() -> APIRouter:
    """Create management router."""
    router = APIRouter(tags=["Management"])

    @router.post("/cleanup")
    async def cleanup_requests(force: bool = False):
        """Manually cleanup stuck requests."""
        cleanup_stuck_requests(force)
        return JSONResponse(content={"status": "cleanup completed"})

    return router