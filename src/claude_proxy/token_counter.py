"""
Token counter using tiktoken for accurate token estimation.
"""

import json
from typing import List, Optional, Union

import tiktoken

from . import models
from .logger import LogEvent, LogRecord, _logger


def count_tokens_for_request(
    messages: List[models.Message],
    system: Optional[Union[str, List[models.SystemContent]]],
    model_name: str,
    tools: Optional[List[models.Tool]] = None,
) -> int:
    """
    Counts tokens for messages and system prompt using tiktoken.

    Args:
        messages: List of Anthropic Message objects.
        system: Optional system prompt string or list of SystemContent.
        model_name: The target model name.
        tools: Optional list of Anthropic Tool objects.

    Returns:
        Estimated token count for the request.
    """
    enc = tiktoken.encoding_for_model("gpt-4")
    total_tokens = 0

    if isinstance(system, str):
        total_tokens += len(enc.encode(system))
    elif isinstance(system, list):
        for block in system:
            if isinstance(block, models.SystemContent) and block.type == "text":
                total_tokens += len(enc.encode(block.text))

    for msg in messages:
        total_tokens += 1

        if isinstance(msg.content, str):
            total_tokens += len(enc.encode(msg.content))
        elif isinstance(msg.content, list):
            for block in msg.content:
                if isinstance(block, models.ContentBlockText):
                    total_tokens += len(enc.encode(block.text))
                elif isinstance(block, models.ContentBlockToolUse):
                    total_tokens += len(enc.encode(block.name))
                    try:
                        input_str = json.dumps(block.input)
                        total_tokens += len(enc.encode(input_str))
                    except Exception as e:
                        _logger.warning(
                            LogRecord(
                                event=LogEvent.TOOL_INPUT_SERIALIZATION_FAILURE.value,
                                message=f"Failed to serialize tool input for token counting: {e}",
                                data={"tool_name": block.name},
                            )
                        )
                elif isinstance(block, models.ContentBlockToolResult):
                    try:
                        if isinstance(block.content, str):
                            total_tokens += len(enc.encode(block.content))
                        else:
                            content_str = json.dumps(block.content)
                            total_tokens += len(enc.encode(content_str))
                    except Exception as e:
                        _logger.warning(
                            LogRecord(
                                event=LogEvent.TOOL_RESULT_SERIALIZATION_FAILURE.value,
                                message=f"Failed to serialize tool result for token counting: {e}",
                            )
                        )

    if tools:
        for tool in tools:
            total_tokens += len(enc.encode(tool.name))
            if tool.description:
                total_tokens += len(enc.encode(tool.description))
            try:
                schema_str = json.dumps(tool.input_schema)
                total_tokens += len(enc.encode(schema_str))
            except Exception as e:
                _logger.warning(
                    LogRecord(
                        event=LogEvent.TOOL_INPUT_SERIALIZATION_FAILURE.value,
                        message=f"Failed to serialize tool schema for token counting: {e}",
                        data={"tool_name": tool.name},
                    )
                )

    _logger.debug(
        LogRecord(
            event=LogEvent.TOKEN_COUNT.value,
            message=f"Counted {total_tokens} tokens for request",
            data={"model": model_name, "token_count": total_tokens},
        )
    )

    return total_tokens
