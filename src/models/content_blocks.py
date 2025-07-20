"""Content block models for message content."""

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel


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


class ContentBlockThinking(BaseModel):
    type: Literal["thinking"]
    thinking: str


# Union type for all content blocks
ContentBlock = Union[
    ContentBlockText, 
    ContentBlockImage, 
    ContentBlockToolUse, 
    ContentBlockToolResult,
    ContentBlockThinking
]