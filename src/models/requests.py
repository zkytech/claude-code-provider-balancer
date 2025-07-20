"""Request models for API endpoints."""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, field_validator, ConfigDict

from .messages import Message, SystemContent
from .tools import Tool, ToolChoice


class MessagesRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    
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
    provider: Optional[str] = None

    @field_validator("max_tokens")
    def check_max_tokens(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("max_tokens must be greater than 0")
        if v > 100000:  # 设置合理的上限
            raise ValueError("max_tokens must not exceed 100,000")
        return v

    @field_validator("top_k")
    def check_top_k(cls, v: Optional[int]) -> Optional[int]:
        if v is not None:
            # Get request_id from context if available
            req_id = None
            try:
                import contextvars
                if hasattr(contextvars, 'copy_context'):
                    ctx = contextvars.copy_context()
                    req_id = ctx.get("request_id", None)
            except:
                pass
                
            try:
                from log_utils import warning, LogRecord, LogEvent
                warning(
                    LogRecord(
                        event=LogEvent.PARAMETER_UNSUPPORTED.value,
                        message="Parameter 'top_k' provided by client but is not directly supported by the OpenAI Chat Completions API and will be ignored.",
                        request_id=req_id,
                        data={"parameter": "top_k", "value": v},
                    )
                )
            except ImportError:
                try:
                    from log_utils.handlers import warning, LogRecord, LogEvent
                    warning(
                        LogRecord(
                            event=LogEvent.PARAMETER_UNSUPPORTED.value,
                            message="Parameter 'top_k' provided by client but is not directly supported by the OpenAI Chat Completions API and will be ignored.",
                            request_id=req_id,
                            data={"parameter": "top_k", "value": v},
                        )
                    )
                except ImportError:
                    pass  # Skip logging if module not available
        return v


class TokenCountRequest(BaseModel):
    model: str
    messages: List[Message]
    system: Optional[Union[str, List[SystemContent]]] = None
    tools: Optional[List[Tool]] = None