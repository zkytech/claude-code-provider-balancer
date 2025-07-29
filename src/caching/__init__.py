"""
Request caching and deduplication system.

This module provides functionality for:
- Generating request signatures for deduplication
- Handling duplicate requests
- Caching responses
- Managing concurrent request processing
"""

from .deduplication import (
    cleanup_stuck_requests,
    generate_request_signature,
    cleanup_completed_request,
    complete_and_cleanup_request,
    complete_and_cleanup_request_delayed,
    handle_duplicate_request,
    simulate_testing_delay,
    extract_content_from_sse_chunks
)

__all__ = [
    "cleanup_stuck_requests",
    "generate_request_signature",
    "cleanup_completed_request",
    "complete_and_cleanup_request",
    "complete_and_cleanup_request_delayed",
    "handle_duplicate_request",
    "extract_content_from_sse_chunks",
    "simulate_testing_delay"
]