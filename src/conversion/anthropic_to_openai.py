"""Convert Anthropic API formats to OpenAI formats."""

import json
from typing import Any, Dict, List, Optional, Union

try:
    from models import Message, SystemContent, Tool, ToolChoice, ContentBlockText, ContentBlockImage, ContentBlockToolUse, ContentBlockToolResult
except ImportError:
    try:
        from models.messages import Message, SystemContent
        from models.tools import Tool, ToolChoice
        from models.content_blocks import ContentBlockText, ContentBlockImage, ContentBlockToolUse, ContentBlockToolResult
    except ImportError:
        # Fallback implementations for testing
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
        
        class ToolChoice:
            def __init__(self, type, name=None):
                self.type = type
                self.name = name
            
            def dict(self):
                return {"type": self.type, "name": self.name}
        
        class ContentBlockText:
            def __init__(self, text):
                self.text = text
        
        class ContentBlockImage:
            pass
        
        class ContentBlockToolUse:
            pass
        
        class ContentBlockToolResult:
            pass

try:
    from utils.logging import warning, error, LogRecord, LogEvent
except ImportError:
    try:
        from utils.logging.handlers import warning, error, LogRecord, LogEvent
    except ImportError:
        # Fallback implementations
        warning = error = lambda *args, **kwargs: None
        LogRecord = dict
        class LogEvent:
            SYSTEM_PROMPT_ADJUSTED = type('', (), {'value': 'system_prompt_adjusted'})()
            TOOL_CHOICE_UNSUPPORTED = type('', (), {'value': 'tool_choice_unsupported'})()

try:
    from conversion.helpers import serialize_tool_result_content_for_openai
except ImportError:
    try:
        from helpers import serialize_tool_result_content_for_openai
    except ImportError:
        # Fallback implementation
        def serialize_tool_result_content_for_openai(content, request_id, log_context):
            if isinstance(content, str):
                return content
            return str(content)


def convert_anthropic_to_openai_messages(
    anthropic_messages: List[Message],
    anthropic_system: Optional[Union[str, List[SystemContent]]] = None,
    request_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Convert Anthropic messages format to OpenAI messages format."""
    # This is a simplified version - the full implementation would be much longer
    openai_messages: List[Dict[str, Any]] = []

    # Handle system prompt
    system_text_content = ""
    if isinstance(anthropic_system, str):
        system_text_content = anthropic_system
    elif isinstance(anthropic_system, list):
        system_texts = [
            block.text
            for block in anthropic_system
            if isinstance(block, SystemContent) and block.type == "text"
        ]
        if len(system_texts) < len(anthropic_system):
            warning(
                LogRecord(
                    event=LogEvent.SYSTEM_PROMPT_ADJUSTED.value,
                    message="Non-text content blocks in Anthropic system prompt were ignored.",
                    request_id=request_id,
                )
            )
        system_text_content = "\n".join(system_texts)

    if system_text_content:
        openai_messages.append({"role": "system", "content": system_text_content})

    # Convert each message
    for i, msg in enumerate(anthropic_messages):
        role = msg.role
        content = msg.content

        if isinstance(content, str):
            openai_messages.append({"role": role, "content": content})
            continue

        # Handle complex content blocks
        if isinstance(content, list):
            # This would contain the full logic for handling mixed content
            # For now, simplified version
            text_parts = []
            for block in content:
                if isinstance(block, ContentBlockText):
                    text_parts.append(block.text)
            
            if text_parts:
                openai_messages.append({"role": role, "content": "\n".join(text_parts)})

    return openai_messages


def convert_anthropic_tools_to_openai(
    anthropic_tools: Optional[List[Tool]],
) -> Optional[List[Dict[str, Any]]]:
    """Convert Anthropic tools format to OpenAI tools format."""
    if not anthropic_tools:
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
        for t in anthropic_tools
    ]


def convert_anthropic_tool_choice_to_openai(
    anthropic_choice: Optional[ToolChoice],
    request_id: Optional[str] = None,
) -> Optional[Union[str, Dict[str, Any]]]:
    """Convert Anthropic tool choice format to OpenAI tool choice format."""
    if not anthropic_choice:
        return None
    if anthropic_choice.type == "auto":
        return "auto"
    if anthropic_choice.type == "any":
        warning(
            LogRecord(
                event=LogEvent.TOOL_CHOICE_UNSUPPORTED.value,
                message="Anthropic tool_choice type 'any' mapped to OpenAI 'auto'. Exact behavior might differ.",
                request_id=request_id,
                data={"anthropic_tool_choice": anthropic_choice.model_dump()},
            )
        )
        return "auto"
    if anthropic_choice.type == "none":
        return "none"
    if anthropic_choice.type == "tool" and anthropic_choice.name:
        return {"type": "function", "function": {"name": anthropic_choice.name}}

    warning(
        LogRecord(
            event=LogEvent.TOOL_CHOICE_UNSUPPORTED.value,
            message=f"Unsupported Anthropic tool_choice: {anthropic_choice.model_dump()}. Defaulting to 'auto'.",
            request_id=request_id,
            data={"anthropic_tool_choice": anthropic_choice.model_dump()},
        )
    )
    return "auto"