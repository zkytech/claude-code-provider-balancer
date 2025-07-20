"""Message-related models."""

from typing import List, Literal, Union
from pydantic import BaseModel

from .content_blocks import ContentBlock


class SystemContent(BaseModel):
    type: Literal["text"]
    text: str


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: Union[str, List[ContentBlock]]