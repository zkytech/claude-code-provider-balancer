# -*- coding: utf-8 -*-
"""
Pydantic models defining the Anthropic API request/response structures.
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any, Optional, Union, Literal
from .logging_config import logger  # Use relative import


# --- Content Block Types ---
class ContentBlockText(BaseModel):
    type: Literal["text"]
    text: str


class ContentBlockImageSource(BaseModel):
    type: str  # e.g., "base64"
    media_type: str  # e.g., "image/jpeg"
    data: str  # Base64 encoded string


class ContentBlockImage(BaseModel):
    type: Literal["image"]
    source: ContentBlockImageSource


class ContentBlockToolUse(BaseModel):
    type: Literal["tool_use"]
    id: str
    name: str
    input: Dict[str, Any]


class ContentBlockToolResult(BaseModel):
    type: Literal["tool_result"]
    tool_use_id: str
    content: Union[
        str, List[Dict[str, Any]], List[Any]
    ]  # Allow string or list for content
    is_error: Optional[bool] = None


# Union of all possible content block types
ContentBlock = Union[
    ContentBlockText, ContentBlockImage, ContentBlockToolUse, ContentBlockToolResult
]


# --- System Prompt Content ---
# Although Anthropic allows multiple system blocks, we simplify based on current usage
class SystemContent(BaseModel):
    type: Literal["text"]
    text: str


# --- Message Structure ---
class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: Union[str, List[ContentBlock]]  # Can be simple string or list of blocks


# --- Tool Definition ---
class Tool(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Dict[str, Any]  # JSON Schema for tool parameters


# --- Tool Choice ---
class ToolChoice(BaseModel):
    type: Literal["auto", "any", "tool"]
    name: Optional[str] = None  # Required if type is "tool"


# --- Main Request Model ---
class MessagesRequest(BaseModel):
    model: str  # Client requested model name (e.g., claude-3-opus-...)
    max_tokens: int
    messages: List[Message]
    system: Optional[Union[str, List[SystemContent]]] = None  # System prompt
    stop_sequences: Optional[List[str]] = None
    stream: Optional[bool] = False
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None  # Note: Not supported by OpenAI API, will warn
    metadata: Optional[Dict[str, Any]] = None  # e.g., {"user_id": "..."}
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[ToolChoice] = None

    @field_validator("top_k")
    def check_top_k(cls, v):
        if v is not None:
            logger.warning(
                "Param 'top_k' provided but ignored (not supported by OpenAI API)."
            )
        return v  # Return the value even if ignored


# --- Token Count Request Model ---
class TokenCountRequest(BaseModel):
    model: str  # Client requested model name
    messages: List[Message]
    system: Optional[Union[str, List[SystemContent]]] = None
    # Tools are not typically included in token count requests, but added for potential future use
    tools: Optional[List[Tool]] = None


# --- Token Count Response Model ---
class TokenCountResponse(BaseModel):
    input_tokens: int


# --- Usage Statistics Model ---
class Usage(BaseModel):
    input_tokens: int
    output_tokens: int


# --- Main Response Model ---
class MessagesResponse(BaseModel):
    id: str  # Message ID (e.g., "msg_...")
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    model: str  # Model that generated the response (should match request model)
    content: List[ContentBlock]  # Response content blocks
    stop_reason: Optional[
        Literal["end_turn", "max_tokens", "stop_sequence", "tool_use", "error"]
    ] = None
    stop_sequence: Optional[str] = None  # If stopped by a sequence
    usage: Usage  # Token usage information
