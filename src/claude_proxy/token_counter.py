"""
Simplified token counter that returns zero values.
"""

from typing import Any, Dict, List, Optional, Union

from . import models
from .logging_config import logger


def count_tokens_for_request(
    messages: List[models.Message],
    system: Optional[Union[str, List[models.SystemContent]]],
    model_name: str,
    tools: Optional[List[models.Tool]] = None,
) -> int:
    """
    Returns zero tokens for all requests.
    Real token counting has been removed for simplicity.

    Args:
        messages: List of Anthropic Message objects.
        system: Optional system prompt string or list of SystemContent.
        model_name: The target model name (unused).
        tools: Optional list of Anthropic Tool objects (unused).

    Returns:
        Always returns 0 tokens.
    """
    logger.debug(f"Token counting disabled - returning 0 for model: {model_name}")
    return 0
