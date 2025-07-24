"""
Streaming module for handling parallel client broadcasting and stream management.
"""

from .parallel_broadcaster import (
    ParallelBroadcaster, 
    ClientStream, 
    create_broadcaster,
    register_broadcaster,
    unregister_broadcaster,
    handle_duplicate_stream_request,
    has_active_broadcaster
)
# Removed validation import - now using src/validation/provider_health.py

__all__ = [
    "ParallelBroadcaster", 
    "ClientStream", 
    "create_broadcaster",
    "register_broadcaster",
    "unregister_broadcaster", 
    "handle_duplicate_stream_request",
    "has_active_broadcaster"
]