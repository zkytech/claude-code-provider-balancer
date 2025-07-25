"""
Management API routes for Claude Code Provider Balancer.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from caching import cleanup_stuck_requests
from core.provider_manager import ProviderManager


def create_management_router(provider_manager: ProviderManager = None) -> APIRouter:
    """Create management router."""
    router = APIRouter(tags=["Management"])

    @router.post("/cleanup")
    async def cleanup_requests(force: bool = False):
        """Manually cleanup stuck requests."""
        cleanup_stuck_requests(force)
        return JSONResponse(content={"status": "cleanup completed"})

    @router.post("/providers/reload")
    async def reload_providers_config():
        """Manually reload provider configuration from config.yaml."""
        if not provider_manager:
            return JSONResponse(
                content={"error": "Provider manager not available"}, 
                status_code=500
            )
        
        try:
            provider_manager.reload_config()
            return JSONResponse(content={
                "status": "success",
                "message": "Provider configuration reloaded successfully",
                "providers_count": len(provider_manager.providers),
                "healthy_providers": len(provider_manager.get_healthy_providers())
            })
        except Exception as e:
            return JSONResponse(
                content={
                    "status": "error", 
                    "message": f"Failed to reload configuration: {str(e)}"
                }, 
                status_code=500
            )

    return router