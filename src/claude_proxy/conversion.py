"""
Handles conversion between Anthropic and OpenAI API formats, including streaming,
with enhanced error handling and consistent request ID usage.
Removes streaming token estimation. Clarifies ID generation needs.
"""

import json
import uuid
from typing import (Any, AsyncGenerator, Dict, List, Literal, Optional, Tuple,
                    Union)

import openai
import tiktoken
from openai import (APIConnectionError, APIError, APITimeoutError,
                    AuthenticationError, BadRequestError, InternalServerError,
                    NotFoundError, PermissionDeniedError, RateLimitError,
                    UnprocessableEntityError)

from . import logger, models
from .models import extract_provider_error_details
from .logger import LogEvent, LogRecord

StopReasonType = Optional[
    Literal["end_turn", "max_tokens", "stop_sequence", "tool_use", "error"]
]


def convert_anthropic_to_openai_messages(
    anthropic_messages: List[models.Message],
    anthropic_system: Optional[Union[str, List[models.SystemContent]]] = None,
    request_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Converts Anthropic messages/system prompt to OpenAI message list format.

    Args:
        anthropic_messages: List of Anthropic message objects.
        anthropic_system: Optional system prompt as string or list of SystemContent blocks.
        request_id: The unique ID for this request cycle, for logging.

    Returns:
        List of OpenAI-formatted message dictionaries.
    """
    openai_messages = []

    system_text_content = ""
    if isinstance(anthropic_system, str):
        system_text_content = anthropic_system
    elif isinstance(anthropic_system, list):
        system_texts = []
        ignored_system_blocks = False
        for block in anthropic_system:
            if isinstance(block, models.SystemContent) and block.type == "text":
                system_texts.append(block.text)
            else:
                ignored_system_blocks = True
        system_text_content = "\n".join(system_texts)

        if ignored_system_blocks:
            logger.warning(
                LogRecord(
                    event=LogEvent.SYSTEM_PROMPT_ADJUSTED.value,
                    message="Non-text content blocks in Anthropic system prompt were ignored.",
                    request_id=request_id,
                )
            )
    if system_text_content:
        openai_messages.append({"role": "system", "content": system_text_content})

    for i, msg in enumerate(anthropic_messages):
        role = msg.role
        content = msg.content

        if isinstance(content, str):
            openai_messages.append({"role": role, "content": content})
            continue

        if isinstance(content, list):
            openai_content_list = []
            tool_results = []
            assistant_tool_calls = []
            text_content = []
            ignored_user_image_source = False

            if not content:
                openai_messages.append({"role": role, "content": ""})
                continue

            for block_idx, block in enumerate(content):
                block_log_ctx = {
                    "anthropic_message_index": i,
                    "block_index": block_idx,
                    "block_type": block.type,
                }

                if isinstance(block, models.ContentBlockText):
                    text_content.append(block.text)
                    if role == "user":
                        openai_content_list.append({"type": "text", "text": block.text})

                elif isinstance(block, models.ContentBlockImage) and role == "user":
                    if block.source.type == "base64":
                        openai_content_list.append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{block.source.media_type};base64,{block.source.data}"
                                },
                            }
                        )
                    else:
                        ignored_user_image_source = True

                elif (
                    isinstance(block, models.ContentBlockToolUse)
                    and role == "assistant"
                ):
                    try:
                        args_str = json.dumps(block.input)
                    except TypeError as e:
                        logger.error(
                            LogRecord(
                                event=LogEvent.TOOL_INPUT_SERIALIZATION_FAILURE.value,
                                message=f"Failed to serialize tool input dictionary to JSON: {e}. Using empty JSON.",
                                request_id=request_id,
                                data={
                                    **block_log_ctx,
                                    "tool_id": block.id,
                                    "tool_name": block.name,
                                },
                            ),
                            e,
                        )
                        args_str = "{}"
                    except Exception as e:
                        logger.error(
                            LogRecord(
                                event=LogEvent.TOOL_INPUT_SERIALIZATION_FAILURE.value,
                                message=f"Unexpected error serializing tool input: {e}. Using empty JSON.",
                                request_id=request_id,
                                data={
                                    **block_log_ctx,
                                    "tool_id": block.id,
                                    "tool_name": block.name,
                                },
                            ),
                            e,
                        )
                        args_str = "{}"

                    assistant_tool_calls.append(
                        {
                            "id": block.id,
                            "type": "function",
                            "function": {"name": block.name, "arguments": args_str},
                        }
                    )

                elif (
                    isinstance(block, models.ContentBlockToolResult) and role == "user"
                ):
                    logger.debug(
                        LogRecord(
                            event=LogEvent.TOOL_RESULT_PROCESSING.value,
                            message="Processing tool result content before serialization",
                            request_id=request_id,
                            data={
                                **block_log_ctx,
                                "tool_use_id": block.tool_use_id,
                                "content_type": str(type(block.content)),
                                "content_repr": repr(block.content),
                                "is_error": block.is_error,
                            }
                        )
                    )
                    content_str = _serialize_tool_result(
                        block.content, request_id, block_log_ctx
                    )
                    logger.debug(
                        LogRecord(
                            event=LogEvent.TOOL_RESULT_PROCESSING.value,
                            message="Tool result content after serialization",
                            request_id=request_id,
                            data={
                                **block_log_ctx,
                                "tool_use_id": block.tool_use_id,
                                "serialized_content": content_str
                            }
                        )
                    )
                    tool_results.append(
                        {
                            "role": "tool",
                            "tool_call_id": block.tool_use_id,
                            "content": content_str,
                        }
                    )

            if ignored_user_image_source:
                logger.warning(
                    LogRecord(
                        event=LogEvent.IMAGE_FORMAT_UNSUPPORTED.value,
                        message=f"Image blocks with source type other than 'base64' were ignored in user message {i}.",
                        request_id=request_id,
                        data={"anthropic_message_index": i},
                    )
                )

            if role == "user":
                if openai_content_list:
                    is_multi_modal = any(
                        item["type"] != "text" for item in openai_content_list
                    )
                    if is_multi_modal or len(openai_content_list) > 1:
                        content_value = openai_content_list
                    elif openai_content_list:
                        content_value = openai_content_list[0]["text"]
                    else:
                        content_value = ""

                    if content_value or not tool_results:
                        openai_messages.append(
                            {
                                "role": "user",
                                "content": content_value or "",
                            }
                        )
                openai_messages.extend(tool_results)

            elif role == "assistant":
                filtered_text = [t for t in text_content if t is not None]
                if filtered_text:
                    openai_messages.append(
                        {
                            "role": "assistant",
                            "content": "\n".join(filtered_text),
                        }
                    )
                if assistant_tool_calls:
                    openai_messages.append(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": assistant_tool_calls,
                        }
                    )

    validated_messages = []
    for msg in openai_messages:
        if (
            msg["role"] == "assistant"
            and msg.get("tool_calls")
            and msg.get("content") is not None
        ):
            logger.warning(
                LogRecord(
                    event=LogEvent.MESSAGE_FORMAT_NORMALIZED.value,
                    message="Corrected assistant message with tool_calls to have content: None.",
                    request_id=request_id,
                    data={"original_content": msg["content"]},
                )
            )
            msg["content"] = None
        validated_messages.append(msg)

    return validated_messages


def _serialize_tool_result(
    content: Any, request_id: Optional[str], log_context: Dict
) -> str:
    """
    Helper to serialize Anthropic tool result content to string for OpenAI.
    """
    try:
        logger.debug(
            LogRecord(
                event=LogEvent.TOOL_RESULT_PROCESSING.value,
                message="Serializing tool result content",
                request_id=request_id,
                data={
                    **log_context,
                    "content_type": str(type(content)),
                    "content_repr": repr(content),
                    "is_list": isinstance(content, list),
                    "is_string": isinstance(content, str),
                }
            )
        )

        if isinstance(content, list):
            text_parts = [
                item.get("text")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            if text_parts:
                result = "\n".join(text_parts)
                logger.debug(
                    LogRecord(
                        event=LogEvent.TOOL_RESULT_PROCESSING.value,
                        message="Joined text parts from list",
                        request_id=request_id,
                        data={
                            **log_context,
                            "text_parts_count": len(text_parts),
                            "result": result
                        }
                    )
                )
                return result
            result = json.dumps(content)
            logger.debug(
                LogRecord(
                    event=LogEvent.TOOL_RESULT_PROCESSING.value,
                    message="Serialized non-text list content",
                    request_id=request_id,
                    data={
                        **log_context,
                        "result": result
                    }
                )
            )
            return result
        elif isinstance(content, str):
            if content == "{}":
                logger.warning(
                    LogRecord(
                        event=LogEvent.TOOL_RESULT_PROCESSING.value,
                        message="Received literal string '{}' as tool result",
                        request_id=request_id,
                        data=log_context
                    )
                )
            return content
        else:
            result = json.dumps(content)
            logger.debug(
                LogRecord(
                    event=LogEvent.TOOL_RESULT_PROCESSING.value,
                    message="Serialized non-string non-list content",
                    request_id=request_id,
                    data={
                        **log_context,
                        "result": result
                    }
                )
            )
            return result
    except TypeError as e:
        logger.warning(
            LogRecord(
                event=LogEvent.TOOL_RESULT_SERIALIZATION_FAILURE.value,
                message=f"Failed to serialize tool result content to JSON: {e}. Returning error JSON.",
                request_id=request_id,
                data=log_context,
            )
        )
        return json.dumps(
            {"error": "Serialization failed", "original_type": str(type(content))}
        )
    except Exception as e:
        logger.warning(
            LogRecord(
                event=LogEvent.TOOL_RESULT_SERIALIZATION_FAILURE.value,
                message=f"Unexpected error serializing tool result content: {e}. Returning error JSON.",
                request_id=request_id,
                data=log_context,
            )
        )
        return json.dumps(
            {
                "error": "Unexpected serialization error",
                "original_type": str(type(content)),
            }
        )


def convert_anthropic_tools_to_openai(
    tools: Optional[List[models.Tool]],
) -> Optional[List[Dict[str, Any]]]:
    """Converts Anthropic tool definitions to OpenAI tool format."""
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.input_schema,
            },
        }
        for t in tools
    ]


def convert_anthropic_tool_choice_to_openai(
    choice: Optional[models.ToolChoice],
    request_id: Optional[str] = None,
) -> Optional[Union[str, Dict[str, Any]]]:
    """Converts Anthropic tool choice to OpenAI tool choice format."""
    if not choice:
        return None

    if choice.type == "auto":
        return "auto"
    if choice.type == "any":
        return "auto"
    if choice.type == "tool" and choice.name:
        return {"type": "function", "function": {"name": choice.name}}

    logger.warning(
        LogRecord(
            event=LogEvent.TOOL_CHOICE_UNSUPPORTED.value,
            message=f"Unsupported Anthropic tool_choice type: '{choice.type}'. Defaulting to 'auto'.",
            request_id=request_id,
            data={
                "tool_choice_type": choice.type,
                "choice_details": choice.model_dump(),
            },
        )
    )
    return "auto"


def convert_openai_to_anthropic(
    openai_response: openai.types.chat.ChatCompletion,
    original_model_name: str,
    request_id: Optional[str] = None,
) -> models.MessagesResponse:
    """Converts a non-streaming OpenAI response to an Anthropic MessagesResponse."""
    anthropic_content: List[models.ContentBlock] = []
    anthropic_stop_reason: StopReasonType = None
    anthropic_stop_sequence: Optional[str] = None

    stop_reason_map: Dict[Optional[str], StopReasonType] = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
        "function_call": "tool_use",
        "content_filter": "stop_sequence",
        None: "end_turn",
    }

    if openai_response.choices:
        choice = openai_response.choices[0]
        message = choice.message
        finish_reason = choice.finish_reason

        anthropic_stop_reason = stop_reason_map.get(finish_reason, "end_turn")

        if message.content:
            anthropic_content.append(
                models.ContentBlockText(type="text", text=message.content)
            )

        if message.tool_calls:
            for call in message.tool_calls:
                if call.type == "function":
                    tool_id = call.id
                    name = call.function.name
                    args_str = call.function.arguments
                    tool_input: Dict[str, Any] = {}

                    try:
                        parsed_input = json.loads(args_str)
                        if isinstance(parsed_input, dict):
                            tool_input = parsed_input
                        else:
                            logger.warning(
                                LogRecord(
                                    event=LogEvent.TOOL_ARGS_TYPE_MISMATCH.value,
                                    message="OpenAI tool args JSON parsed to non-dict. Wrapping.",
                                    request_id=request_id,
                                    data={
                                        "tool_name": name,
                                        "tool_id": tool_id,
                                        "type": str(type(parsed_input)),
                                    },
                                )
                            )
                            tool_input = {"value": parsed_input}
                    except json.JSONDecodeError as e:
                        logger.error(
                            LogRecord(
                                event=LogEvent.TOOL_ARGS_PARSE_FAILURE.value,
                                message="Failed to parse OpenAI tool args JSON. Storing raw.",
                                request_id=request_id,
                                data={
                                    "tool_name": name,
                                    "tool_id": tool_id,
                                    "raw_args": args_str,
                                },
                            ),
                            e,
                        )
                        tool_input = {
                            "error": "Failed to parse arguments JSON",
                            "raw_arguments": args_str,
                        }
                    except Exception as e:
                        logger.error(
                            LogRecord(
                                event=LogEvent.TOOL_ARGS_UNEXPECTED.value,
                                message="Unexpected error processing OpenAI tool args.",
                                request_id=request_id,
                                data={
                                    "tool_name": name,
                                    "tool_id": tool_id,
                                    "raw_args": args_str,
                                },
                            ),
                            e,
                        )
                        tool_input = {
                            "error": f"Unexpected error: {e}",
                            "raw_arguments": args_str,
                        }

                    anthropic_content.append(
                        models.ContentBlockToolUse(
                            type="tool_use", id=tool_id, name=name, input=tool_input
                        )
                    )

            if finish_reason in ["tool_calls", "function_call"]:
                anthropic_stop_reason = "tool_use"

    if not anthropic_content:
        anthropic_content.append(models.ContentBlockText(type="text", text=""))

    usage = openai_response.usage
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0
    anthropic_usage = models.Usage(
        input_tokens=input_tokens, output_tokens=output_tokens
    )

    response_id = f"msg_{openai_response.id}"

    return models.MessagesResponse(
        id=response_id,
        type="message",
        role="assistant",
        model=original_model_name,
        content=anthropic_content,
        stop_reason=anthropic_stop_reason,
        stop_sequence=anthropic_stop_sequence,
        usage=anthropic_usage,
    )



def _get_anthropic_error_details(
    exc: Exception,
) -> Tuple[models.AnthropicErrorType, str, Optional[models.ProviderErrorMetadata]]:
    """
    Maps caught exceptions to Anthropic error types and messages,
    and extracts provider-specific details if available.

    Args:
        exc: The exception to map

    Returns:
        Tuple containing (AnthropicErrorType enum, error_message, provider_details)
    """
    provider_details: Optional[models.ProviderErrorMetadata] = None
    error_message = str(exc)
    error_type = models.AnthropicErrorType.API_ERROR  # Default

    # Attempt to extract provider details from APIError body
    if isinstance(exc, APIError) and hasattr(exc, "body") and isinstance(exc.body, dict):
        provider_details = extract_provider_error_details(exc.body.get("error", {}))

    # Map specific exception types
    if isinstance(exc, AuthenticationError):
        error_type = models.AnthropicErrorType.AUTHENTICATION
    elif isinstance(exc, RateLimitError):
        error_type = models.AnthropicErrorType.RATE_LIMIT
    elif isinstance(exc, BadRequestError):
        error_type = models.AnthropicErrorType.INVALID_REQUEST
    elif isinstance(exc, PermissionDeniedError):
        error_type = models.AnthropicErrorType.PERMISSION
    elif isinstance(exc, NotFoundError):
        error_type = models.AnthropicErrorType.NOT_FOUND
    elif isinstance(exc, UnprocessableEntityError):
        error_type = models.AnthropicErrorType.INVALID_REQUEST
    elif isinstance(exc, InternalServerError):
        error_type = models.AnthropicErrorType.API_ERROR
    elif isinstance(exc, APIConnectionError):
        error_type = models.AnthropicErrorType.API_ERROR
        error_message = f"Connection error: {exc}"
    elif isinstance(exc, APITimeoutError):
        error_type = models.AnthropicErrorType.API_ERROR
        error_message = f"Timeout error: {exc}"
    elif isinstance(exc, APIError):  # Catch broader APIError after specific ones
        status_code = exc.status_code if hasattr(exc, "status_code") else 500
        default_error = (
            models.AnthropicErrorType.API_ERROR
            if status_code >= 500
            else models.AnthropicErrorType.INVALID_REQUEST
        )
        error_type = models.STATUS_CODE_ERROR_MAP.get(status_code, default_error)
        error_message = f"API error (Status {status_code}): {exc}"
    else:  # Fallback for unexpected errors
        error_type = models.AnthropicErrorType.API_ERROR
        error_message = f"Unexpected error: {exc}"

    return error_type, error_message, provider_details


def _format_anthropic_error_sse(
    error_type: models.AnthropicErrorType,
    message: str,
    provider_details: Optional[models.ProviderErrorMetadata] = None,
) -> str:
    """
    Formats an error into the Anthropic SSE error event structure.

    Creates a consistent error response in Server-Sent Events (SSE) format
    for streaming responses. This matches the structure used by the Anthropic API
    for streaming errors and ensures error format consistency between
    streaming and non-streaming responses.

    Examples:
        Basic error:
        ```python
        _format_anthropic_error_sse(
            models.AnthropicErrorType.INVALID_REQUEST,
            "Invalid parameter"
        )
        ```

    Args:
        error_type: Anthropic error type enum
        message: Error message
        provider_details: Optional provider error metadata

    Returns:
        A formatted SSE event string for the error
    """
    error = models.AnthropicErrorDetail(type=error_type, message=message)

    if provider_details:
        error.provider = provider_details.provider_name

        if (
            provider_details.raw_error
            and isinstance(provider_details.raw_error, dict)
            and "error" in provider_details.raw_error
        ):
            provider_error = provider_details.raw_error["error"]
            if isinstance(provider_error, dict):
                if "message" in provider_error and provider_error["message"]:
                    error.provider_message = provider_error["message"]
                if "code" in provider_error:
                    error.provider_code = provider_error["code"]

    error_response = models.AnthropicErrorResponse(error=error)
    return f"event: error\ndata: {json.dumps(error_response.model_dump())}\n\n"


async def handle_streaming_response(
    openai_stream: openai.AsyncStream[openai.types.chat.ChatCompletionChunk],
    original_model_name: str,
    initial_input_tokens: int,
    request_id: str,
) -> AsyncGenerator[str, None]:
    """
    Consumes an OpenAI stream and yields Anthropic-compatible SSE events.
    Handles errors gracefully and uses consistent request ID. No token estimation.
    """
    message_id = f"msg_stream_{request_id}_{uuid.uuid4().hex[:8]}"
    final_stop_reason: StopReasonType = None
    final_stop_sequence: Optional[str] = None
    text_block_started = False
    current_tool_calls: Dict[int, Dict[str, str]] = {}
    sent_tool_block_starts = set()
    output_token_count = 0
    
    enc = tiktoken.encoding_for_model("gpt-4")

    stop_reason_map: Dict[Optional[str], StopReasonType] = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
        "function_call": "tool_use",
        "content_filter": "stop_sequence",
        None: None,
    }

    try:
        start_event_data = {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "model": original_model_name,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": initial_input_tokens, "output_tokens": 0},
            },
        }
        yield f"event: message_start\ndata: {json.dumps(start_event_data)}\n\n"
        yield f"event: ping\ndata: {json.dumps({'type': 'ping'})}\n\n"

        async for chunk in openai_stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            finish_reason = chunk.choices[0].finish_reason

            if delta.content:
                if not text_block_started:
                    start_text_block = {
                        "type": "content_block_start",
                        "index": 0,
                        "content_block": {"type": "text", "text": ""},
                    }
                    yield f"event: content_block_start\ndata: {json.dumps(start_text_block)}\n\n"
                    text_block_started = True
                output_token_count += len(enc.encode(delta.content))
                
                text_delta_event = {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": delta.content},
                }
                yield f"event: content_block_delta\ndata: {json.dumps(text_delta_event)}\n\n"

            if delta.tool_calls:
                for tool_delta in delta.tool_calls:
                    anthropic_idx = tool_delta.index

                    if anthropic_idx not in current_tool_calls:
                        tool_id = (
                            tool_delta.id
                            if tool_delta.id
                            else f"tool_ph_{request_id}_{anthropic_idx}"
                        )
                        current_tool_calls[anthropic_idx] = {
                            "id": tool_id,
                            "name": "",
                            "arguments": "",
                        }
                        if not tool_delta.id:
                            logger.error(
                                LogRecord(
                                    event=LogEvent.TOOL_ID_PLACEHOLDER.value,
                                    request_id=request_id,
                                    message=f"Generated placeholder Tool ID '{tool_id}' for index {anthropic_idx} as OpenAI ID was initially absent.",
                                )
                            )

                    tool_state = current_tool_calls[anthropic_idx]
                    if tool_delta.id and tool_state["id"].startswith("tool_ph_"):
                        logger.debug(
                            LogRecord(
                                event=LogEvent.TOOL_ID_UPDATED.value,
                                request_id=request_id,
                                message=f"Updating placeholder Tool ID '{tool_state['id']}' to '{tool_delta.id}' for index {anthropic_idx}.",
                            )
                        )
                        tool_state["id"] = tool_delta.id
                    if tool_delta.function:
                        if tool_delta.function.name:
                            tool_state["name"] = tool_delta.function.name
                        if tool_delta.function.arguments:
                            tool_state["arguments"] += tool_delta.function.arguments

                    if (
                        anthropic_idx not in sent_tool_block_starts
                        and tool_state["id"]
                        and tool_state["name"]
                    ):
                        start_tool_block = {
                            "type": "content_block_start",
                            "index": anthropic_idx,
                            "content_block": {
                                "type": "tool_use",
                                "id": tool_state["id"],
                                "name": tool_state["name"],
                                "input": {},
                            },
                        }
                        yield f"event: content_block_start\ndata: {json.dumps(start_tool_block)}\n\n"
                        sent_tool_block_starts.add(anthropic_idx)

                    if (
                        tool_delta.function
                        and tool_delta.function.arguments
                        and anthropic_idx in sent_tool_block_starts
                    ):
                        output_token_count += len(enc.encode(tool_delta.function.arguments))
                        
                        args_delta_event = {
                            "type": "content_block_delta",
                            "index": anthropic_idx,
                            "delta": {
                                "type": "input_json_delta",
                                "partial_json": tool_delta.function.arguments,
                            },
                        }
                        yield f"event: content_block_delta\ndata: {json.dumps(args_delta_event)}\n\n"

            if finish_reason:
                final_stop_reason = stop_reason_map.get(finish_reason, "end_turn")
                if finish_reason in ["tool_calls", "function_call"]:
                    final_stop_reason = "tool_use"
                break

        if text_block_started:
            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"
        for idx in sent_tool_block_starts:
            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': idx})}\n\n"

        if final_stop_reason is None:
            final_stop_reason = "end_turn"

        message_delta_event = {
            "type": "message_delta",
            "delta": {
                "stop_reason": final_stop_reason,
                "stop_sequence": final_stop_sequence,
            },
            "usage": {"output_tokens": output_token_count},
        }
        yield f"event: message_delta\ndata: {json.dumps(message_delta_event)}\n\n"
        yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"

    except Exception as e:
        error_type, error_message, provider_details = _get_anthropic_error_details(e)

        logger.error(
            LogRecord(
                event=LogEvent.STREAM_INTERRUPTED.value,
                message=f"Error during OpenAI stream: {error_message}",
                request_id=request_id,
            ),
            e
        )
        yield _format_anthropic_error_sse(error_type, error_message, provider_details)
        return
