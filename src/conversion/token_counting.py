"""Token counting utilities using tiktoken."""

import json
from typing import Dict, List, Optional, Union

import tiktoken

try:
    from models import Message, SystemContent, Tool, ContentBlockText, ContentBlockImage, ContentBlockToolUse, ContentBlockToolResult
except ImportError:
    try:
        from models.messages import Message, SystemContent
        from models.tools import Tool
        from models.content_blocks import ContentBlockText, ContentBlockImage, ContentBlockToolUse, ContentBlockToolResult
    except ImportError:
        # Fallback implementations - basic classes for testing
        class Message:
            def __init__(self, role, content):
                self.role = role
                self.content = content
        
        class SystemContent:
            def __init__(self, type, text):
                self.type = type
                self.text = text
        
        class Tool:
            def __init__(self, name, description=None, input_schema=None):
                self.name = name
                self.description = description
                self.input_schema = input_schema
        
        class ContentBlockText:
            def __init__(self, text):
                self.text = text
        
        class ContentBlockImage:
            pass
        
        class ContentBlockToolUse:
            def __init__(self, name, input):
                self.name = name
                self.input = input
        
        class ContentBlockToolResult:
            def __init__(self, content):
                self.content = content

try:
    from log_utils import warning, debug, LogRecord, LogEvent
except ImportError:
    try:
        from log_utils.handlers import warning, debug, LogRecord, LogEvent
    except ImportError:
        # Fallback implementations
        warning = debug = lambda *args, **kwargs: None
        LogRecord = dict
        class LogEvent:
            TOKEN_ENCODER_LOAD_FAILED = type('', (), {'value': 'token_encoder_load_failed'})()
            TOOL_INPUT_SERIALIZATION_FAILURE = type('', (), {'value': 'tool_input_serialization_failure'})()
            TOOL_RESULT_SERIALIZATION_FAILURE = type('', (), {'value': 'tool_result_serialization_failure'})()
            TOKEN_COUNT = type('', (), {'value': 'token_count'})()


# Cache for token encoders
_token_encoder_cache: Dict[str, tiktoken.Encoding] = {}


def get_token_encoder(
    model_name: str = "gpt-4", request_id: Optional[str] = None
) -> tiktoken.Encoding:
    """Gets a tiktoken encoder, caching it for performance."""

    cache_key = "gpt-4"
    if cache_key not in _token_encoder_cache:
        try:
            _token_encoder_cache[cache_key] = tiktoken.encoding_for_model(cache_key)
        except Exception:
            try:
                _token_encoder_cache[cache_key] = tiktoken.get_encoding("cl100k_base")
                warning(
                    LogRecord(
                        event=LogEvent.TOKEN_ENCODER_LOAD_FAILED.value,
                        message=f"Could not load tiktoken encoder for '{cache_key}', using 'cl100k_base'. Token counts may be approximate.",
                        request_id=request_id,
                        data={"model_tried": cache_key},
                    )
                )
            except Exception as e_cl:
                try:
                    from log_utils.handlers import critical
                    critical(
                        LogRecord(
                            event=LogEvent.TOKEN_ENCODER_LOAD_FAILED.value,
                            message="Failed to load any tiktoken encoder (gpt-4, cl100k_base). Token counting will be inaccurate.",
                            request_id=request_id,
                        ),
                        exc=e_cl,
                    )
                except ImportError:
                    pass  # Skip logging if not available

                class DummyEncoder:
                    def encode(self, text: str) -> List[int]:
                        return list(range(len(text)))

                _token_encoder_cache[cache_key] = DummyEncoder()
    return _token_encoder_cache[cache_key]


def count_tokens_for_anthropic_request(
    messages: List[Message],
    system: Optional[Union[str, List[SystemContent]]],
    model_name: str,
    tools: Optional[List[Tool]] = None,
    request_id: Optional[str] = None,
) -> int:
    """Count tokens for an Anthropic request."""
    enc = get_token_encoder(model_name, request_id)
    total_tokens = 0

    # Count system prompt tokens
    if isinstance(system, str):
        total_tokens += len(enc.encode(system))
    elif isinstance(system, list):
        for block in system:
            if isinstance(block, SystemContent) and block.type == "text":
                total_tokens += len(enc.encode(block.text))

    # Count message tokens
    for msg in messages:
        total_tokens += 4  # Base tokens per message
        if msg.role:
            total_tokens += len(enc.encode(msg.role))

        if isinstance(msg.content, str):
            total_tokens += len(enc.encode(msg.content))
        elif isinstance(msg.content, list):
            for block in msg.content:
                if isinstance(block, ContentBlockText):
                    total_tokens += len(enc.encode(block.text))
                elif isinstance(block, ContentBlockImage):
                    total_tokens += 768  # Estimated tokens for images
                elif isinstance(block, ContentBlockToolUse):
                    total_tokens += len(enc.encode(block.name))
                    try:
                        input_str = json.dumps(block.input)
                        total_tokens += len(enc.encode(input_str))
                    except Exception:
                        warning(
                            LogRecord(
                                event=LogEvent.TOOL_INPUT_SERIALIZATION_FAILURE.value,
                                message="Failed to serialize tool input for token counting.",
                                data={"tool_name": block.name},
                                request_id=request_id,
                            )
                        )
                elif isinstance(block, ContentBlockToolResult):
                    try:
                        content_str = ""
                        if isinstance(block.content, str):
                            content_str = block.content
                        elif isinstance(block.content, list):
                            for item in block.content:
                                if (
                                    isinstance(item, dict)
                                    and item.get("type") == "text"
                                ):
                                    content_str += item.get("text", "")
                                else:
                                    content_str += json.dumps(item)
                        else:
                            content_str = json.dumps(block.content)
                        total_tokens += len(enc.encode(content_str))
                    except Exception:
                        warning(
                            LogRecord(
                                event=LogEvent.TOOL_RESULT_SERIALIZATION_FAILURE.value,
                                message="Failed to serialize tool result for token counting.",
                                request_id=request_id,
                            )
                        )

    # Count tool tokens
    if tools:
        total_tokens += 2  # Base tokens for tools
        for tool in tools:
            total_tokens += len(enc.encode(tool.name))
            if tool.description:
                total_tokens += len(enc.encode(tool.description))
            try:
                schema_str = json.dumps(tool.input_schema)
                total_tokens += len(enc.encode(schema_str))
            except Exception:
                warning(
                    LogRecord(
                        event=LogEvent.TOOL_INPUT_SERIALIZATION_FAILURE.value,
                        message="Failed to serialize tool schema for token counting.",
                        data={"tool_name": tool.name},
                        request_id=request_id,
                    )
                )

    debug(
        LogRecord(
            event=LogEvent.TOKEN_COUNT.value,
            message=f"Estimated {total_tokens} input tokens for model {model_name}",
            data={"model": model_name, "token_count": total_tokens},
            request_id=request_id,
        )
    )
    return total_tokens