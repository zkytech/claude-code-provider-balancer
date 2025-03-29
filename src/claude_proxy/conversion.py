# -*- coding: utf-8 -*-
"""
Handles conversion between Anthropic and OpenAI API formats, including streaming.
"""
import json
import uuid
import openai
from typing import List, Dict, Any, Optional, Union, Literal, AsyncGenerator
from . import models  # Use relative import
from .logging_config import logger, log_error_simplified  # Use relative import

# --- Request Conversion ---


def convert_anthropic_to_openai_messages(
    anthropic_messages: List[models.Message],
    anthropic_system: Optional[Union[str, List[models.SystemContent]]] = None,
) -> List[Dict[str, Any]]:
    """Converts Anthropic messages/system prompt to OpenAI message list format."""
    openai_messages = []

    # Handle System Prompt
    system_text_content = ""
    if isinstance(anthropic_system, str):
        system_text_content = anthropic_system
    elif isinstance(anthropic_system, list):
        # Concatenate text from SystemContent blocks if provided as list
        system_text_content = "\n".join(
            [
                block.text
                for block in anthropic_system
                if isinstance(block, models.SystemContent) and block.type == "text"
            ]
        )
    if system_text_content:
        openai_messages.append({"role": "system", "content": system_text_content})

    # Handle User/Assistant Messages
    for msg in anthropic_messages:
        role = msg.role
        content = msg.content

        if isinstance(content, str):
            # Simple text message
            openai_messages.append({"role": role, "content": content})
        elif isinstance(content, list):
            # Complex message with content blocks
            openai_content_list = []
            tool_results = []
            assistant_tool_calls = []

            for block in content:
                if isinstance(block, models.ContentBlockText):
                    if role == "user":
                        openai_content_list.append({"type": "text", "text": block.text})
                    elif role == "assistant":
                        # Append text to the last assistant message if it was also text,
                        # otherwise start a new assistant message. Avoids empty messages.
                        if (
                            openai_messages
                            and openai_messages[-1]["role"] == "assistant"
                            and isinstance(openai_messages[-1]["content"], str)
                            and not openai_messages[-1].get(
                                "tool_calls"
                            )  # Ensure it wasn't a tool call message
                        ):
                            openai_messages[-1]["content"] += "\n" + block.text
                        else:
                            openai_messages.append(
                                {"role": "assistant", "content": block.text}
                            )
                elif isinstance(block, models.ContentBlockImage) and role == "user":
                    # Convert image block to OpenAI format (only for user role)
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
                    # Convert assistant tool usage block
                    try:
                        # OpenAI expects arguments as a JSON string
                        args_str = json.dumps(block.input)
                    except Exception as e:
                        logger.warning(
                            f"Failed to dump tool input JSON: {e}. Using empty object."
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
                    # Convert user-provided tool result block
                    try:
                        # Attempt to serialize content, default to string representation
                        if isinstance(block.content, list):
                            # Extract text if it's a list of text blocks, else dump JSON
                            text_parts = [
                                item.get("text")
                                for item in block.content
                                if isinstance(item, dict) and item.get("type") == "text"
                            ]
                            content_str = (
                                "\n".join(text_parts)
                                if text_parts
                                else json.dumps(block.content)
                            )
                        elif isinstance(block.content, str):
                            content_str = block.content
                        else:
                            # Handle other types (e.g., dict) by dumping JSON
                            content_str = json.dumps(block.content)
                    except Exception as e:
                        logger.warning(
                            f"Failed to serialize tool result content: {e}. Using error message."
                        )
                        content_str = json.dumps(
                            {
                                "error": "Serialization failed",
                                "original_type": str(type(block.content)),
                            }
                        )

                    tool_results.append(
                        {
                            "role": "tool",
                            "tool_call_id": block.tool_use_id,
                            "content": content_str,
                        }
                    )

            # Append accumulated content/results for the current message
            if role == "user":
                if openai_content_list:
                    openai_messages.append(
                        {"role": "user", "content": openai_content_list}
                    )
                # Append tool results *after* the user message content they correspond to
                openai_messages.extend(tool_results)
            elif role == "assistant":
                # Check if the last message was an assistant message without tool calls
                last_msg_is_assistant_text = (
                    openai_messages
                    and openai_messages[-1]["role"] == "assistant"
                    and isinstance(openai_messages[-1]["content"], str)
                    and not openai_messages[-1].get("tool_calls")
                )

                if assistant_tool_calls:
                    # If the last message was assistant text, create a *new* assistant message for tool calls.
                    # Otherwise, append to the last assistant message if it already has tool calls,
                    # or create a new one if the last message wasn't an assistant message.
                    if (
                        openai_messages
                        and openai_messages[-1]["role"] == "assistant"
                        and openai_messages[-1].get(
                            "tool_calls"
                        )  # Already has tool calls
                    ):
                        openai_messages[-1]["tool_calls"].extend(assistant_tool_calls)
                    else:
                        # Create a new assistant message specifically for tool calls
                        openai_messages.append(
                            {
                                "role": "assistant",
                                "content": None,  # OpenAI requires content=None if tool_calls present
                                "tool_calls": assistant_tool_calls,
                            }
                        )

    # Final pass: Ensure assistant messages with tool_calls have content=None
    for msg in openai_messages:
        if (
            msg["role"] == "assistant"
            and msg.get("tool_calls")
            and msg.get("content") is not None  # Check if content is not already None
        ):
            # This case should ideally be handled above, but as a safeguard:
            # If an assistant message has both text content accumulated AND tool calls,
            # it's ambiguous. Prioritize tool calls as per OpenAI spec.
            # Log a warning.
            logger.warning(
                f"Assistant message has both text content and tool calls. Setting content to None. Original text: {msg['content']}"
            )
            msg["content"] = None

    return openai_messages


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
                "description": t.description or "",  # Ensure description is present
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
        return None  # Default behavior (usually "auto")

    if choice.type == "auto":
        return "auto"  # OpenAI equivalent
    if choice.type == "any":
        # OpenAI uses "required" to force calling *some* function
        return "required"
    if choice.type == "tool" and choice.name:
        # Force calling a specific function
        return {"type": "function", "function": {"name": choice.name}}

    # Fallback or if type is invalid, default to auto
    logger.warning(
        f"Unsupported Anthropic tool_choice type: {choice.type}. Defaulting to 'auto'."
    )
    return "auto"


# --- Response Conversion ---


def convert_openai_to_anthropic(
    openai_response: openai.types.chat.ChatCompletion, original_model_name: str
) -> models.MessagesResponse:
    """Converts a non-streaming OpenAI response to an Anthropic MessagesResponse."""
    anthropic_content: List[models.ContentBlock] = []
    # Define the type directly using Literal as in the model definition
    StopReasonType = Optional[
        Literal["end_turn", "max_tokens", "stop_sequence", "tool_use", "error"]
    ]
    anthropic_stop_reason: StopReasonType = None
    anthropic_stop_sequence: Optional[str] = None

    # Map OpenAI finish reasons to Anthropic stop reasons
    stop_reason_map: Dict[Optional[str], StopReasonType] = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
        "content_filter": "stop_sequence",  # Assuming content filter maps here
        None: "end_turn",  # If reason is missing, assume normal end
    }

    if openai_response.choices:
        choice = openai_response.choices[0]
        message = choice.message
        finish_reason = choice.finish_reason

        anthropic_stop_reason = stop_reason_map.get(
            finish_reason, "end_turn"
        )  # Default to end_turn

        # Add text content if present
        if message.content:
            anthropic_content.append(
                models.ContentBlockText(type="text", text=message.content)
            )

        # Add tool calls if present
        if message.tool_calls:
            for call in message.tool_calls:
                if call.type == "function":
                    tool_id = call.id
                    name = call.function.name
                    args_str = call.function.arguments
                    try:
                        # Parse the arguments string into a dict
                        tool_input = json.loads(args_str)
                    except json.JSONDecodeError:
                        logger.warning(
                            f"Failed to parse tool arguments JSON for tool {name} (ID: {tool_id}). Raw: {args_str}"
                        )
                        tool_input = {
                            "error": "Failed to parse arguments JSON",
                            "raw_arguments": args_str,
                        }
                    except Exception as e:  # Catch other potential errors
                        logger.error(
                            f"Unexpected error parsing tool arguments for tool {name} (ID: {tool_id}): {e}"
                        )
                        tool_input = {
                            "error": f"Unexpected error during argument parsing: {e}",
                            "raw_arguments": args_str,
                        }

                    # Ensure tool_input is a dictionary, as expected by Anthropic model
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
            # If the stop reason was tool_calls, ensure it's set correctly
            if finish_reason == "tool_calls":
                anthropic_stop_reason = "tool_use"

    # Ensure there's at least one content block (even if empty)
    if not anthropic_content:
        anthropic_content.append(models.ContentBlockText(type="text", text=""))

    # Extract usage statistics
    usage = openai_response.usage
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0
    anthropic_usage = models.Usage(
        input_tokens=input_tokens, output_tokens=output_tokens
    )

    # Construct the response ID
    response_id = f"msg_{openai_response.id}"  # Prepend "msg_"

    return models.MessagesResponse(
        id=response_id,
        model=original_model_name,  # Use the model requested by the client
        content=anthropic_content,
        stop_reason=anthropic_stop_reason,
        stop_sequence=anthropic_stop_sequence,  # Currently not mapped from OpenAI
        usage=anthropic_usage,
    )


# --- Streaming Response Conversion ---


async def handle_streaming_response(
    openai_stream: openai.AsyncStream[openai.types.chat.ChatCompletionChunk],
    original_model_name: str,
    initial_input_tokens: int,
    request_id: str,  # Pass request ID for logging context
) -> AsyncGenerator[str, None]:
    """
    Consumes an OpenAI stream and yields Anthropic-compatible SSE events.
    """
    message_id = f"msg_stream_{uuid.uuid4()}"  # Unique ID for this stream message
    output_token_count = 0  # Track output tokens for final usage
    # Define the type directly using Literal as in the model definition
    StopReasonType = Optional[
        Literal["end_turn", "max_tokens", "stop_sequence", "tool_use", "error"]
    ]
    final_stop_reason: StopReasonType = None
    final_stop_sequence: Optional[str] = None
    content_block_index = 0  # Index for content blocks (text is 0, tools start from 1)
    text_block_started = False
    # Store partial tool call info: {anthropic_index: {"id": ..., "name": ..., "arguments": ...}}
    current_tool_calls: Dict[int, Dict[str, str]] = {}
    # Keep track of which tool block starts have been sent to avoid duplicates
    sent_tool_block_starts = set()

    # Map OpenAI finish reasons to Anthropic stop reasons
    stop_reason_map: Dict[Optional[str], StopReasonType] = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
        "content_filter": "stop_sequence",
        None: None,  # Keep None as None until the end
    }

    try:
        # 1. Send message_start event
        start_event_data = {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "model": original_model_name,
                "content": [],  # Content starts empty
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {
                    "input_tokens": initial_input_tokens,
                    "output_tokens": 0,
                },  # Initial usage
            },
        }
        yield f"event: message_start\ndata: {json.dumps(start_event_data)}\n\n"

        # 2. Send initial ping
        yield f"event: ping\ndata: {json.dumps({'type': 'ping'})}\n\n"

        # 3. Process OpenAI stream chunks
        async for chunk in openai_stream:
            if not chunk.choices:
                continue  # Skip empty chunks

            delta = chunk.choices[0].delta
            finish_reason = chunk.choices[0].finish_reason

            # Estimate token usage (simple approximation)
            if delta.content:
                output_token_count += 1  # Rough estimate
            if delta.tool_calls:
                # Estimate tokens per tool call chunk (very rough)
                output_token_count += len(delta.tool_calls) * 5

            # --- Handle Text Delta ---
            if delta.content:
                if not text_block_started:
                    # Send content_block_start for the text block (index 0)
                    start_text_block = {
                        "type": "content_block_start",
                        "index": 0,
                        "content_block": {
                            "type": "text",
                            "text": "",
                        },  # Start with empty text
                    }
                    yield f"event: content_block_start\ndata: {json.dumps(start_text_block)}\n\n"
                    text_block_started = True

                # Send content_block_delta for text
                text_delta_event = {
                    "type": "content_block_delta",
                    "index": 0,  # Text is always index 0
                    "delta": {"type": "text_delta", "text": delta.content},
                }
                yield f"event: content_block_delta\ndata: {json.dumps(text_delta_event)}\n\n"

            # --- Handle Tool Call Delta ---
            if delta.tool_calls:
                for tool_delta in delta.tool_calls:
                    # Anthropic tool indices start from 0, but text is block 0,
                    # so tool blocks effectively start at index 1 relative to Anthropic spec if text exists.
                    # However, OpenAI indices start at 0 for tools. Let's use OpenAI's index directly
                    # for internal tracking and map it for Anthropic events.
                    openai_tool_index = tool_delta.index
                    # Anthropic index: if text exists, add 1, otherwise use openai index.
                    # Let's simplify and always use openai_tool_index + 1 if text_block_started, else openai_tool_index
                    # Correction: Anthropic index seems to be independent for each type. Text is index 0. First tool is index 0 of tool_calls.
                    # Let's stick to OpenAI index for internal dict key and use it directly for Anthropic index.
                    anthropic_idx = openai_tool_index

                    # Initialize or update tool state
                    if anthropic_idx not in current_tool_calls:
                        # Initialize with potentially partial info
                        current_tool_calls[anthropic_idx] = {
                            "id": tool_delta.id
                            or f"tool_{uuid.uuid4()}",  # Generate ID if missing early
                            "name": tool_delta.function.name or "",
                            "arguments": tool_delta.function.arguments or "",
                        }
                    else:
                        # Update existing tool state with new delta info
                        if tool_delta.id:  # ID might arrive later
                            current_tool_calls[anthropic_idx]["id"] = tool_delta.id
                        if tool_delta.function.name:  # Name might arrive later
                            current_tool_calls[anthropic_idx][
                                "name"
                            ] = tool_delta.function.name
                        if tool_delta.function.arguments:  # Append argument chunks
                            current_tool_calls[anthropic_idx][
                                "arguments"
                            ] += tool_delta.function.arguments

                    tool_state = current_tool_calls[anthropic_idx]

                    # Send content_block_start for the tool if ID and Name are known and not sent yet
                    if (
                        anthropic_idx not in sent_tool_block_starts
                        and tool_state["id"]  # Ensure ID is present
                        and tool_state["name"]  # Ensure Name is present
                    ):
                        start_tool_block = {
                            "type": "content_block_start",
                            "index": anthropic_idx,  # Use the tool's own index
                            "content_block": {
                                "type": "tool_use",
                                "id": tool_state["id"],
                                "name": tool_state["name"],
                                "input": {},  # Input starts empty
                            },
                        }
                        yield f"event: content_block_start\ndata: {json.dumps(start_tool_block)}\n\n"
                        sent_tool_block_starts.add(anthropic_idx)

                    # Send content_block_delta for tool arguments if available and start was sent
                    if (
                        tool_delta.function.arguments
                        and anthropic_idx in sent_tool_block_starts
                    ):
                        args_delta_event = {
                            "type": "content_block_delta",
                            "index": anthropic_idx,
                            "delta": {
                                "type": "input_json_delta",  # Anthropic type for arg deltas
                                "partial_json": tool_delta.function.arguments,
                            },
                        }
                        yield f"event: content_block_delta\ndata: {json.dumps(args_delta_event)}\n\n"

            # --- Handle Finish Reason ---
            if finish_reason:
                final_stop_reason = stop_reason_map.get(finish_reason, "end_turn")
                # We don't map stop_sequence from OpenAI stream finish reasons easily
                break  # Exit loop once finish reason is received

        # 4. Send content_block_stop events
        if text_block_started:
            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"
        for idx in sent_tool_block_starts:
            yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': idx})}\n\n"

        # 5. Send message_delta event with final usage and stop reason
        # Ensure final_stop_reason is not None; default to 'end_turn' if stream ended without explicit reason
        if final_stop_reason is None:
            final_stop_reason = "end_turn"

        message_delta_event = {
            "type": "message_delta",
            "delta": {
                "stop_reason": final_stop_reason,
                "stop_sequence": final_stop_sequence,  # Remains None currently
            },
            "usage": {"output_tokens": output_token_count},  # Final output token count
        }
        yield f"event: message_delta\ndata: {json.dumps(message_delta_event)}\n\n"

        # 6. Send final message_stop event
        yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"

    except openai.APIError as e:
        # Log specific details from APIError if available
        error_detail = f"Stream Error (APIError) in handle_streaming_response: {e}"
        error_body = getattr(e, 'body', None)
        if error_body:
            error_detail += f" | Body: {error_body}"
            logger.error(
                f"ID: {request_id} OpenAI APIError Body: {error_body}",
                extra={"request_id": request_id}
            )

        log_error_simplified(request_id, e, 500, 0, error_detail)
        try:
            # Try to inform the client via an error event
            error_payload = {
                "type": "error",
                "error": {
                    "type": "api_error", # More specific type
                    "message": f"An error occurred during streaming from the provider: {e}",
                    "provider_message": str(error_body) if error_body else str(e) # Include body if possible
                },
            }
            yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"
            # Still send message_stop after error event if possible
            yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
        except Exception as write_err:
            # Log error during error reporting
            logger.error(
                f"ID: {request_id} Failed to send stream APIError event to client: {write_err}"
            )
        # Re-raise the exception so the main handler knows something went wrong
        raise
    except Exception as e: # Catch other non-APIError exceptions
        # Log the generic error using the simplified logger
        log_error_simplified(
            request_id, e, 500, 0, f"Stream Error (General Exception) in handle_streaming_response: {e}"
        )
        try:
            # Try to inform the client via an error event
            error_payload = {
                "type": "error",
                "error": {
                    "type": "internal_server_error", # Keep generic for non-API errors
                    "message": f"An unexpected error occurred during streaming: {e}",
                },
            }
            yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"
            # Still send message_stop after error event if possible
            yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"
        except Exception as write_err:
            # Log error during error reporting
            logger.error(
                f"ID: {request_id} Failed to send stream general error event to client: {write_err}"
            )
        # Re-raise the exception so the main handler knows something went wrong
        raise

    finally:
        # Clean up resources if any were allocated (e.g., closing connections if manually managed)
        # In this case, the openai_stream context manager handles cleanup.
        pass
