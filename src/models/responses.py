"""Response models for API endpoints."""

from typing import List, Literal, Optional
from pydantic import BaseModel

from .content_blocks import ContentBlock


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int


class TokenCountResponse(BaseModel):
    input_tokens: int


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