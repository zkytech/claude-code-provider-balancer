"""
Unified mock server router for simplified testing.
"""

from fastapi import APIRouter, Request, HTTPException
from .test_context import TestContextManager
from .response_generator import MockResponseGenerator


def create_unified_mock_router() -> APIRouter:
    """Create unified mock router that handles all provider requests."""
    router = APIRouter()
    
    @router.post("/mock-provider/{provider_name}/v1/messages")
    async def unified_mock_provider(provider_name: str, request: Request):
        """
        Unified mock provider handler.
        
        This single endpoint replaces dozens of specialized mock endpoints.
        It dynamically generates responses based on the current test scenario.
        """
        try:
            # Get current test context
            test_context = TestContextManager.get_current_context()
            if not test_context:
                # For now, return a default success response when no context is set
                # This allows direct testing of the mock server without TestEnvironment
                from .test_scenario import ProviderConfig, ProviderBehavior
                
                default_config = ProviderConfig(
                    provider_name,
                    ProviderBehavior.SUCCESS,
                    response_data={"content": f"Default response from {provider_name}"}
                )
                
                request_data = await request.json()
                response = await MockResponseGenerator.generate(
                    behavior=default_config.behavior,
                    request_data=request_data,
                    provider_config=default_config
                )
                return response
            
            # Get provider configuration
            provider_config = test_context.get_provider_config(provider_name)
            if not provider_config:
                raise HTTPException(
                    status_code=404,
                    detail=f"Provider '{provider_name}' not found in current test scenario"
                )
            
            # Parse request data
            request_data = await request.json()
            
            # Generate response based on provider behavior
            response = await MockResponseGenerator.generate(
                behavior=provider_config.behavior,
                request_data=request_data,
                provider_config=provider_config
            )
            
            return response
            
        except Exception as e:
            # Log error for debugging
            import logging
            logging.error(f"Mock provider error for {provider_name}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Mock provider error: {str(e)}")
    
    @router.get("/mock-provider/{provider_name}/health")
    async def mock_provider_health(provider_name: str):
        """Health check for mock providers."""
        test_context = TestContextManager.get_current_context()
        if not test_context:
            return {"status": "no_context", "provider": provider_name}
        
        provider_config = test_context.get_provider_config(provider_name)
        if not provider_config:
            return {"status": "not_found", "provider": provider_name}
        
        return {
            "status": "ok",
            "provider": provider_name,
            "behavior": provider_config.behavior.value,
            "scenario": test_context.name
        }
    
    @router.post("/mock-set-context")
    async def set_test_context(request: Request):
        """Set test context from external request (for cross-process communication)."""
        try:
            context_data = await request.json()
            
            # Reconstruct TestScenario from JSON data
            from .test_scenario import TestScenario, ProviderConfig, ProviderBehavior, ExpectedBehavior
            
            providers = []
            for p_data in context_data.get("providers", []):
                provider = ProviderConfig(
                    name=p_data["name"],
                    behavior=ProviderBehavior(p_data["behavior"]),
                    response_data=p_data.get("response_data"),
                    delay_ms=p_data.get("delay_ms", 0),
                    priority=p_data.get("priority", 1),
                    error_count=p_data.get("error_count", 0),
                    error_http_code=p_data.get("error_http_code", 500),
                    error_message=p_data.get("error_message", "Mock provider error")
                )
                providers.append(provider)
            
            scenario = TestScenario(
                name=context_data["name"],
                providers=providers,
                expected_behavior=ExpectedBehavior(context_data.get("expected_behavior", "success")),
                model_name=context_data.get("model_name"),
                description=context_data.get("description")
            )
            
            TestContextManager.set_scenario(scenario)
            
            return {"status": "success", "message": f"Test context set to scenario: {scenario.name}"}
            
        except Exception as e:
            import logging
            logging.error(f"Failed to set test context: {str(e)}")
            return {"status": "error", "message": f"Failed to set test context: {str(e)}"}
    
    @router.delete("/mock-clear-context")
    async def clear_test_context():
        """Clear current test context."""
        TestContextManager.clear()
        return {"status": "success", "message": "Test context cleared"}

    @router.get("/mock-test-context")
    async def get_test_context():
        """Get current test context for debugging."""
        test_context = TestContextManager.get_current_context()
        if not test_context:
            return {"context": None}
        
        return {
            "context": {
                "scenario_name": test_context.name,
                "expected_behavior": test_context.expected_behavior.value,
                "providers": [
                    {
                        "name": p.name,
                        "behavior": p.behavior.value,
                        "priority": p.priority,
                        "response_data": p.response_data,
                        "delay_ms": p.delay_ms
                    }
                    for p in test_context.providers
                ]
            }
        }
    
    return router