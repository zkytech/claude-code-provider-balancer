"""
Handles conversion between Anthropic and OpenAI API formats, including streaming.
"""

import json
import uuid
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional, Union

import openai

from . import models
from .logging_config import log_error_simplified, logger


def convert_anthropic_to_openai_messages(
    anthropic_messages: List[models.Message],
    anthropic_system: Optional[Union[str, List[models.SystemContent]]] = None,
) -> List[Dict[str, Any]]:
    """
    Converts Anthropic messages/system prompt to OpenAI message list format.

    Args:
        anthropic_messages: List of Anthropic message objects
        anthropic_system: Optional system prompt as string or list of SystemContent blocks

    Returns:
        List of OpenAI-formatted message dictionaries
    """
    openai_messages = []

    system_text_content = ""
    if isinstance(anthropic_system, str):
        system_text_content = anthropic_system
    elif isinstance(anthropic_system, list):
        system_text_content = "\n".join(
            [
                block.text
                for block in anthropic_system
                if isinstance(block, models.SystemContent) and block.type == "text"
            ]
        )
    if system_text_content:
        openai_messages.append({"role": "system", "content": system_text_content})

    for msg in anthropic_messages:
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

            for block in content:
                if isinstance(block, models.ContentBlockText):
                    text_content.append(block.text)
                    if role == "user":
                        openai_content_list.append({"type": "text", "text": block.text})

                elif isinstance(block, models.ContentBlockImage) and role == "user":
                    openai_content_list.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{block.source.media_type};base64,{block.source.data}"
                            },
                        }
                    )

                elif (
                    isinstance(block, models.ContentBlockToolUse)
                    and role == "assistant"
                ):
                    try:
                        args_str = json.dumps(block.input)
                    except Exception as e:
                        logger.warning(f"Failed to serialize tool input: {e}")
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
                    content_str = _serialize_tool_result(block.content)
                    tool_results.append(
                        {
                            "role": "tool",
                            "tool_call_id": block.tool_use_id,
                            "content": content_str,
                        }
                    )

            if role == "user":
                if openai_content_list:
                    openai_messages.append(
                        {
                            "role": "user",
                            "content": (
                                openai_content_list
                                if len(openai_content_list) > 1
                                else openai_content_list[0]["text"]
                            ),
                        }
                    )
                openai_messages.extend(tool_results)

            elif role == "assistant":
                if text_content:
                    text_msg = {"role": "assistant", "content": "\n".join(text_content)}
                    openai_messages.append(text_msg)

                if assistant_tool_calls:
                    tool_msg = {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": assistant_tool_calls,
                    }
                    openai_messages.append(tool_msg)

    def _ensure_message_format(msg):
        """Ensures each message follows OpenAI's format requirements"""
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            if msg.get("content") is not None:
                logger.warning(
                    f"Assistant message has both content and tool_calls. Setting content to None. Content was: {msg['content']}"
                )
                msg["content"] = None
        return msg

    openai_messages = [_ensure_message_format(msg) for msg in openai_messages]

    return openai_messages


def _serialize_tool_result(content) -> str:
    """Helper method to serialize tool result content to string format"""
    try:
        if isinstance(content, list):
            text_parts = [
                item.get("text")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            if text_parts:
                return "\n".join(text_parts)
            return json.dumps(content)
        elif isinstance(content, str):
            return content
        else:
            return json.dumps(content)
    except Exception as e:
        logger.warning(f"Failed to serialize tool result content: {e}")
        return json.dumps(
            {"error": "Serialization failed", "original_type": str(type(content))}
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
        f"Unsupported Anthropic tool_choice type: {choice.type}. Defaulting to 'auto'."
    )
    return "auto"


def convert_openai_to_anthropic(
    openai_response: openai.types.chat.ChatCompletion, original_model_name: str
) -> models.MessagesResponse:
    """Converts a non-streaming OpenAI response to an Anthropic MessagesResponse."""
    anthropic_content: List[models.ContentBlock] = []
    StopReasonType = Optional[
        Literal["end_turn", "max_tokens", "stop_sequence", "tool_use", "error"]
    ]
    anthropic_stop_reason: StopReasonType = None
    anthropic_stop_sequence: Optional[str] = None

    stop_reason_map: Dict[Optional[str], StopReasonType] = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
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
                    try:
                        tool_input = json.loads(args_str)
                    except json.JSONDecodeError:
                        logger.warning(
                            f"Failed to parse tool arguments JSON for tool {name} (ID: {tool_id}). Raw: {args_str}"
                        )
                        tool_input = {
                            "error": "Failed to parse arguments JSON",
                            "raw_arguments": args_str,
                        }
                    except Exception as e:
                        logger.error(
                            f"Unexpected error parsing tool arguments for tool {name} (ID: {tool_id}): {e}"
                        )
                        tool_input = {
                            "error": f"Unexpected error during argument parsing: {e}",
                            "raw_arguments": args_str,
                        }

                    if not isinstance(tool_input, dict):
                        logger.warning(
                            f"Tool arguments for {name} (ID: {tool_id}) parsed to non-dict type ({type(tool_input)}). Wrapping in 'value'."
                        )
                        tool_input = {"value": tool_input}

                    anthropic_content.append(
                        models.ContentBlockToolUse(
                            type="tool_use", id=tool_id, name=name, input=tool_input
                        )
                    )
            if finish_reason == "tool_calls":
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
        model=original_model_name,
        content=anthropic_content,
        stop_reason=anthropic_stop_reason,
        stop_sequence=anthropic_stop_sequence,
        usage=anthropic_usage,
    )


async def handle_streaming_response(
    openai_stream: openai.AsyncStream[openai.types.chat.ChatCompletionChunk],
    original_model_name: str,
    initial_input_tokens: int,
    request_id: str,
) -> AsyncGenerator[str, None]:
    """
    Consumes an OpenAI stream and yields Anthropic-compatible SSE events.
    """
    message_id = f"msg_stream_{uuid.uuid4()}"
    StopReasonType = Optional[
        Literal["end_turn", "max_tokens", "stop_sequence", "tool_use", "error"]
    ]
    final_stop_reason: StopReasonType = None
    final_stop_sequence: Optional[str] = None
    content_block_index = 0
    text_block_started = False
    current_tool_calls: Dict[int, Dict[str, str]] = {}
    sent_tool_block_starts = set()

    stop_reason_map: Dict[Optional[str], StopReasonType] = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
        "content_filter": "stop_sequence",
        None: None,
    }

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
            "usage": {
                "input_tokens": initial_input_tokens,
                "output_tokens": 0,
            },
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
                    "content_block": {
                        "type": "text",
                        "text": "",
                    },
                }
                yield f"event: content_block_start\ndata: {json.dumps(start_text_block)}\n\n"
                text_block_started = True

            text_delta_event = {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": delta.content},
            }
            yield f"event: content_block_delta\ndata: {json.dumps(text_delta_event)}\n\n"

        if delta.tool_calls:
            for tool_delta in delta.tool_calls:
                openai_tool_index = tool_delta.index
                anthropic_idx = openai_tool_index

                if anthropic_idx not in current_tool_calls:
                    current_tool_calls[anthropic_idx] = {
                        "id": tool_delta.id or f"tool_{uuid.uuid4()}",
                        "name": tool_delta.function.name or "",
                        "arguments": tool_delta.function.arguments or "",
                    }
                else:
                    if tool_delta.id:
                        current_tool_calls[anthropic_idx]["id"] = tool_delta.id
                    if tool_delta.function.name:
                        current_tool_calls[anthropic_idx][
                            "name"
                        ] = tool_delta.function.name
                    if tool_delta.function.arguments:
                        current_tool_calls[anthropic_idx][
                            "arguments"
                        ] += tool_delta.function.arguments

                tool_state = current_tool_calls[anthropic_idx]

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
                    tool_delta.function.arguments
                    and anthropic_idx in sent_tool_block_starts
                ):
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
        "usage": {"output_tokens": 0},
    }
    yield f"event: message_delta\ndata: {json.dumps(message_delta_event)}\n\n"

    yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
