# -*- coding: utf-8 -*-
"""
Provides token counting functionality using tiktoken.
"""
import tiktoken
import json
from typing import List, Dict, Any, Optional, Union
from . import models  # Use relative import
from .logging_config import logger  # Use relative import
from .conversion import convert_anthropic_to_openai_messages  # Use relative import

# --- Token Counting Constants ---
# Heuristics based on OpenAI's cookbook and observed behavior
TOKENS_PER_MESSAGE = 3  # Base cost per message
TOKENS_PER_NAME = 1  # Cost for role/name if present

# --- Encoding Cache ---
# Cache encodings to avoid repeated lookups
_encoding_cache: Dict[str, tiktoken.Encoding] = {}
DEFAULT_ENCODING = "cl100k_base"  # Common default for many models


def _get_encoding(model_name: str) -> tiktoken.Encoding:
    """Gets the tiktoken encoding for a model, using a cache and defaults."""
    # Simple mapping (can be expanded)
    if model_name.startswith(
        ("openai/gpt-4", "openai/gpt-3.5", "google/", "anthropic/claude-3")
    ):
        encoding_name = "cl100k_base"
    elif model_name.startswith("mistral"):
        encoding_name = "cl100k_base"  # Approximation for Mistral models
    # Add mappings for other models if known
    else:
        encoding_name = DEFAULT_ENCODING
        logger.debug(
            f"Using default encoding '{DEFAULT_ENCODING}' for model: {model_name}"
        )

    if encoding_name not in _encoding_cache:
        try:
            _encoding_cache[encoding_name] = tiktoken.get_encoding(encoding_name)
            logger.debug(f"Cached encoding '{encoding_name}'")
        except Exception as e:
            logger.warning(
                f"Failed to get encoding '{encoding_name}', falling back to '{DEFAULT_ENCODING}'. Error: {e}"
            )
            # Cache the default encoding under the failed name to avoid retrying
            if DEFAULT_ENCODING not in _encoding_cache:
                try:
                    _encoding_cache[DEFAULT_ENCODING] = tiktoken.get_encoding(
                        DEFAULT_ENCODING
                    )
                except Exception as default_e:
                    logger.error(
                        f"CRITICAL: Failed to get default encoding '{DEFAULT_ENCODING}'. Token counting will be inaccurate. Error: {default_e}"
                    )
                    # Return a dummy object that might allow partial counting or raise errors later
                    return tiktoken.get_encoding(
                        DEFAULT_ENCODING
                    )  # Let it raise if default fails critically
            _encoding_cache[encoding_name] = _encoding_cache[DEFAULT_ENCODING]

    return _encoding_cache[encoding_name]


def count_tokens_for_request(
    messages: List[models.Message],
    system: Optional[Union[str, List[models.SystemContent]]],
    model_name: str,
    # Tools are generally not counted precisely in input tokens this way,
    # but placeholder for potential future refinement if needed.
    tools: Optional[List[models.Tool]] = None,
) -> int:
    """
    Estimates the number of input tokens for an Anthropic request payload
    by converting it to the OpenAI format and using tiktoken heuristics.

    Args:
        messages: List of Anthropic Message objects.
        system: Optional system prompt string or list of SystemContent.
        model_name: The target model name (used to select encoding).
        tools: Optional list of Anthropic Tool objects (currently ignored in count).

    Returns:
        Estimated number of input tokens.
    """
    logger.debug(f"Counting tokens for model: {model_name}")
    encoding = _get_encoding(model_name)

    # Convert Anthropic messages/system to OpenAI format first
    try:
        openai_messages = convert_anthropic_to_openai_messages(messages, system)
    except Exception as e:
        logger.error(
            f"Failed to convert messages for token counting: {e}. Returning 0.",
            exc_info=True,
        )
        return 0

    num_tokens = 0
    for message in openai_messages:
        num_tokens += TOKENS_PER_MESSAGE
        for key, value in message.items():
            try:
                # Count tokens for string values (role, content text)
                if isinstance(value, str):
                    num_tokens += len(encoding.encode(value))
                # Count tokens for the 'name' field if present (e.g., in tool calls/results)
                if key == "name":
                    num_tokens += TOKENS_PER_NAME
                # Handle complex content (list of blocks, e.g., user message with image)
                elif isinstance(value, list) and key == "content":
                    for item in value:
                        if isinstance(item, dict):
                            if item.get("type") == "text":
                                num_tokens += len(encoding.encode(item.get("text", "")))
                            elif item.get("type") == "image_url":
                                # Token cost for images is complex and model-dependent.
                                # Using a rough placeholder or ignoring might be necessary.
                                # Let's ignore for now as it's highly variable.
                                logger.debug(
                                    "Ignoring image content block in token count estimation."
                                )
                                pass
                # Handle tool calls (list of dicts) - encode the JSON representation
                elif isinstance(value, list) and key == "tool_calls":
                    # Encode the JSON representation of the tool calls list
                    try:
                        tool_calls_str = json.dumps(value)
                        num_tokens += len(encoding.encode(tool_calls_str))
                    except Exception as json_e:
                        logger.warning(
                            f"Could not encode tool_calls for token counting: {json_e}"
                        )

            except Exception as enc_e:
                logger.warning(
                    f"Could not encode key '{key}' value '{str(value)[:50]}...' for token counting: {enc_e}"
                )

    # Add fixed tokens for the overall structure (end of conversation)
    num_tokens += 3  # Based on OpenAI cookbook example, represents priming tokens like <|endofprompt|>

    # Note: Tool definitions themselves (`tools` parameter) also consume tokens.
    # This is harder to estimate precisely with tiktoken alone.
    # If tools are present, add a rough estimate or implement more detailed counting.
    if tools:
        logger.debug(
            "Tools provided, but precise token counting for tool definitions is not implemented. Count may be underestimated."
        )
        # Example rough estimate: add tokens based on JSON dump size
        # try:
        #     tools_str = json.dumps([t.model_dump() for t in tools])
        #     num_tokens += len(encoding.encode(tools_str)) // 2 # Very rough guess
        # except Exception: pass

    logger.debug(f"Estimated token count: {num_tokens}")
    return num_tokens
