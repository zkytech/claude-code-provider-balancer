"""
Pydantic models defining the Anthropic API request/response structures.
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, field_validator

from . import logger
from .logger import LogEvent, LogRecord


class ContentBlockText(BaseModel):
    type: Literal["text"]
    text: str


class ContentBlockImageSource(BaseModel):
    type: str
    media_type: str
    data: str


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
    content: Union[str, List[Dict[str, Any]], List[Any]]
    is_error: Optional[bool] = None


ContentBlock = Union[
    ContentBlockText, ContentBlockImage, ContentBlockToolUse, ContentBlockToolResult
]


class SystemContent(BaseModel):
    type: Literal["text"]
    text: str


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: Union[str, List[ContentBlock]]


class Tool(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Dict[str, Any]


class ToolChoice(BaseModel):
    type: Literal["auto", "any", "tool"]
    name: Optional[str] = None


class MessagesRequest(BaseModel):
    model: str
    max_tokens: int
    messages: List[Message]
    system: Optional[Union[str, List[SystemContent]]] = None
    stop_sequences: Optional[List[str]] = None
    stream: Optional[bool] = False
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[ToolChoice] = None

    @field_validator("top_k")
    def check_top_k(cls, v: Optional[int]) -> Optional[int]:
        if v is not None:
            logger.warning(
                LogRecord(
                    event=LogEvent.PARAMETER_UNSUPPORTED.value,
                    message="Param 'top_k' provided but ignored (not supported by OpenAI API)",
                )
            )
        return v


class TokenCountRequest(BaseModel):
    model: str
    messages: List[Message]
    system: Optional[Union[str, List[SystemContent]]] = None
    tools: Optional[List[Tool]] = None


class TokenCountResponse(BaseModel):
    input_tokens: int


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int


class ProviderErrorMetadata(BaseModel):
    """
    Provider-specific error metadata as defined by OpenRouter API.

    This model captures provider-specific error details forwarded by OpenRouter.
    Provider errors are included in the OpenRouter error response's metadata field.

    See: https://openrouter.ai/docs/api-reference/errors#provider-errors
    """

    provider_name: str
    raw_error: Optional[Dict[str, Any]] = None


class AnthropicErrorType(str, Enum):
    """
    Standard Anthropic error types for consistent error handling.

    These error types mirror the official Anthropic API error types.
    Ref: https://docs.anthropic.com/claude/reference/errors

    Note: This is a string Enum, making it directly JSON serializable.
    """

    INVALID_REQUEST = "invalid_request_error"
    AUTHENTICATION = "authentication_error"
    PERMISSION = "permission_error"
    NOT_FOUND = "not_found_error"
    RATE_LIMIT = "rate_limit_error"
    API_ERROR = "api_error"
    OVERLOADED = "overloaded_error"
    REQUEST_TOO_LARGE = "request_too_large"


class AnthropicErrorDetail(BaseModel):
    """
    Structured error information compliant with Anthropic API.

    This model defines the structure of error details in Anthropic API responses.
    It includes standard fields from Anthropic plus additional provider-specific
    fields for better error debugging when using third-party models.

    Ref: https://docs.anthropic.com/claude/reference/errors
    """

    type: AnthropicErrorType
    message: str
    provider: Optional[str] = None
    provider_message: Optional[str] = None
    provider_code: Optional[Union[str, int]] = None


class AnthropicErrorResponse(BaseModel):
    """
    Anthropic-compatible error response structure.

    This is the top-level error response model that matches the
    official Anthropic API error response format. It contains
    a constant type field set to "error" and a nested error
    detail object with specifics about the error.

    Ref: https://docs.anthropic.com/claude/reference/errors
    """

    type: Literal["error"] = "error"
    error: AnthropicErrorDetail


class MessagesResponse(BaseModel):
    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    model: str
    content: List[ContentBlock]
    stop_reason: Optional[
        Literal["end_turn", "max_tokens", "stop_sequence", "tool_use", "error"]
    ] = None
    stop_sequence: Optional[str] = None
    usage: Usage
