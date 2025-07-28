"""
Mock provider modules - each module corresponds exactly to a test file.
Strict module isolation to avoid confusion and maintain clear boundaries.
"""

from .common_providers import create_common_provider_routes
from .test_duplicate_request_handling import create_test_duplicate_request_handling_routes
from .test_mixed_provider_responses import create_test_mixed_provider_responses_routes
from .test_multi_provider_management import create_test_multi_provider_management_routes
from .test_non_streaming_requests import create_test_non_streaming_requests_routes
from .test_streaming_requests import create_test_streaming_requests_routes
from .test_unhealthy_counting_unit import create_test_unhealthy_counting_unit_routes


def create_all_mock_provider_routes():
    """Create and combine all mock provider routes."""
    from fastapi import APIRouter
    
    router = APIRouter(prefix="/test-providers", tags=["Mock Providers"])
    
    # Include common providers first (used by multiple test files)
    router.include_router(create_common_provider_routes())
    
    # Include routes for each test file - strict 1:1 mapping
    router.include_router(create_test_duplicate_request_handling_routes())
    router.include_router(create_test_mixed_provider_responses_routes())
    router.include_router(create_test_multi_provider_management_routes())
    router.include_router(create_test_non_streaming_requests_routes())
    router.include_router(create_test_streaming_requests_routes())
    router.include_router(create_test_unhealthy_counting_unit_routes())
    
    return router