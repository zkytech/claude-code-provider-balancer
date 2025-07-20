"""Tool-related models."""

from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field


class Tool(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Dict[str, Any] = Field(..., alias="input_schema")


class ToolChoice(BaseModel):
    type: Literal["auto", "any", "tool", "none"]
    name: Optional[str] = None