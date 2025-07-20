"""Caching and deduplication functionality."""

from .deduplication import (
    cleanup_stuck_requests,
    check_cache_size_limit,
    generate_request_signature,
    cleanup_completed_request,
    complete_and_cleanup_request,
    handle_duplicate_request,
    update_response_cache,
    validate_response_quality,
    simulate_testing_delay,
    debug_compare_provider_response,
    extract_content_from_sse_chunks
)

from .cache_serving import (
    serve_waiting_duplicate_requests,
    serve_from_cache
)

__all__ = [
    "cleanup_stuck_requests",
    "check_cache_size_limit",
    "generate_request_signature",
    "cleanup_completed_request",
    "complete_and_cleanup_request",
    "handle_duplicate_request", 
    "update_response_cache",
    "validate_response_quality",
    "serve_waiting_duplicate_requests",
    "serve_from_cache",
    "extract_content_from_sse_chunks",
    "simulate_testing_delay",
    "debug_compare_provider_response"
]