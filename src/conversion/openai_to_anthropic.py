"""Convert OpenAI API formats to Anthropic formats."""

import json
from typing import Optional

import openai

try:
    from models import MessagesResponse, ContentBlockText, ContentBlockToolUse, Usage
except ImportError:
    # Fallback for nested imports
    from models.responses import MessagesResponse
    from models.content_blocks import ContentBlockText, ContentBlockToolUse
    from models.responses import Usage

try:
    from log_utils import warning, error, LogRecord, LogEvent
except ImportError:
    try:
        from log_utils.handlers import warning, error, LogRecord, LogEvent
    except ImportError:
        # Fallback implementations
        warning = error = lambda *args, **kwargs: None
        LogRecord = dict
        class LogEvent:
            TOOL_ARGS_PARSE_FAILURE = type('', (), {'value': 'tool_args_parse_failure'})()


def convert_openai_to_anthropic_response(
    openai_response: openai.types.chat.ChatCompletion,
    original_anthropic_model_name: str,
    request_id: Optional[str] = None,
) -> MessagesResponse:
    """Convert OpenAI response format to Anthropic response format."""
    # This is a simplified version
    anthropic_content = []
    anthropic_stop_reason = "end_turn"

    if openai_response.choices:
        choice = openai_response.choices[0]
        message = choice.message

        # Handle text content
        if message.content:
            anthropic_content.append(
                ContentBlockText(type="text", text=message.content)
            )

        # Handle tool calls
        if message.tool_calls:
            for call in message.tool_calls:
                if call.type == "function":
                    tool_input_dict = {}
                    try:
                        parsed_input = json.loads(call.function.arguments)
                        if isinstance(parsed_input, dict):
                            tool_input_dict = parsed_input
                        else:
                            tool_input_dict = {"value": parsed_input}
                    except json.JSONDecodeError as e:
                        error(
                            LogRecord(
                                event=LogEvent.TOOL_ARGS_PARSE_FAILURE.value,
                                message=f"Failed to parse JSON arguments for tool '{call.function.name}'.",
                                request_id=request_id,
                                data={
                                    "tool_name": call.function.name,
                                    "tool_id": call.id,
                                    "raw_args": call.function.arguments,
                                },
                            ),
                            exc=e,
                        )
                        tool_input_dict = {"error_parsing_arguments": call.function.arguments}

                    anthropic_content.append(
                        ContentBlockToolUse(
                            type="tool_use",
                            id=call.id,
                            name=call.function.name,
                            input=tool_input_dict,
                        )
                    )
            anthropic_stop_reason = "tool_use"

    # Default content if empty
    if not anthropic_content:
        anthropic_content.append(ContentBlockText(type="text", text=""))

    # Extract usage
    usage = openai_response.usage
    anthropic_usage = Usage(
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
    )

    # Generate response ID
    response_id = (
        f"msg_{openai_response.id}"
        if openai_response.id
        else f"msg_{request_id}_completed"
    )

    return MessagesResponse(
        id=response_id,
        type="message",
        role="assistant",
        model=original_anthropic_model_name,
        content=anthropic_content,
        stop_reason=anthropic_stop_reason,
        usage=anthropic_usage,
    )


async def handle_anthropic_streaming_response_from_openai_stream(
    openai_stream,
    original_anthropic_model_name: str,
    request_id: str,
):
    """Handle streaming response conversion from OpenAI to Anthropic format."""
    # This would be a very complex function in the real implementation
    # For now, just a placeholder
    async for chunk in openai_stream:
        yield f"data: {json.dumps({'type': 'text_delta', 'text': 'Streaming response'})}\n\n"