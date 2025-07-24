"""
Health check and monitoring API routes for Claude Code Provider Balancer.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.provider_manager import ProviderManager


def create_health_router(provider_manager: ProviderManager, app_name: str, app_version: str) -> APIRouter:
    """Create health router with provider manager dependency."""
    router = APIRouter(tags=["Health"])

    @router.get("/", include_in_schema=False)
    async def root_health_check() -> JSONResponse:
        """Basic health check and information endpoint."""
        return JSONResponse(
            content={
                "service": app_name,
                "version": app_version,
                "status": "healthy",
                "providers_available": len(provider_manager.get_healthy_providers()) if provider_manager else 0,
            }
        )

    @router.get("/providers")
    async def get_providers_status() -> JSONResponse:
        """Get status of all configured providers."""
        if not provider_manager:
            return JSONResponse(content={"error": "Provider manager not initialized"})
        
        # Get comprehensive status from provider manager
        status_data = provider_manager.get_status()
        
        # Enhance provider status with model information
        for provider_status in status_data["providers"]:
            provider_name = provider_status["name"]
            
            # Get models for this provider from model_routes
            provider_models = []
            for model_pattern, routes in provider_manager.model_routes.items():
                for route in routes:
                    if route.provider == provider_name and route.enabled:
                        provider_models.append({
                            "pattern": model_pattern,
                            "model": route.model,
                            "priority": route.priority
                        })
            
            provider_status["models"] = provider_models
            
            # Add human-readable status field
            if provider_status["enabled"] and provider_status["healthy"]:
                provider_status["status"] = "healthy"
            elif provider_status["enabled"] and not provider_status["healthy"]:
                provider_status["status"] = "unhealthy"
            else:
                provider_status["status"] = "disabled"
        
        return JSONResponse(content=status_data)

    return router