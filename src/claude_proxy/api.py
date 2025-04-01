"""
FastAPI application definition, endpoints, and request handling logic.
Orchestrates calls to other components (config, models, conversion, etc.).
"""

import json
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union, cast

import fastapi
import openai
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from openai.types.chat import (ChatCompletionMessageParam,
                               ChatCompletionToolParam)
from pydantic import ValidationError

from . import conversion, logger, models
from .config import settings
from .logger import LogRecord
from .openrouter_client import client

app = fastapi.FastAPI(
    title=settings.app_name,
    description="Routes Anthropic API requests to OpenRouter, selecting models dynamically.",
    version=settings.app_version,
    docs_url=None,
    redoc_url=None,
)


def select_target_model(client_model_name: str, request_id: str) -> str:
    """Selects the target OpenRouter model based on the client's request."""
    client_model_lower = client_model_name.lower()

    if "opus" in client_model_lower or "sonnet" in client_model_lower:
        target_model = settings.big_model_name
        logger.debug(
            LogRecord(
                event="model_selection",
                message="Client model mapped to BIG model",
                request_id=request_id,
                data={"client_model": client_model_name, "target_model": target_model},
            )
        )
    elif "haiku" in client_model_lower:
        target_model = settings.small_model_name
        logger.debug(
            LogRecord(
                event="model_selection",
                message="Client model mapped to SMALL model",
                request_id=request_id,
                data={"client_model": client_model_name, "target_model": target_model},
            )
        )
    else:
        target_model = settings.small_model_name
        logger.warning(
            LogRecord(
                event="model_selection",
                message="Unknown client model, defaulting to SMALL model",
                request_id=request_id,
                data={"client_model": client_model_name, "target_model": target_model},
            )
        )
    return target_model


@app.post("/v1/messages", response_model=None, tags=["API"], status_code=200)
async def create_message(request: Request) -> Union[JSONResponse, StreamingResponse]:
    """
    Main endpoint for Anthropic message completions, proxied to OpenRouter.
    Handles conversions, streaming, dynamic model selection, and provider mods.
    Logs requests and errors with traceable IDs.
    """
    request_id = str(uuid.uuid4()).split("-")[0]
    request.state.request_id = request_id
    start_time = time.time()
    is_stream = False

    body = await request.json()

    anthropic_request = models.MessagesRequest.model_validate(body)
    is_stream = anthropic_request.stream or False
    logger.debug(
        LogRecord(
            event="request_validation",
            message="Request body parsed and validated successfully",
            request_id=request_id,
        )
    )

    target_model = select_target_model(anthropic_request.model, request_id)
    target_provider = (
        target_model.split("/")[0].lower() if "/" in target_model else "unknown"
    )
    logger.debug(
        LogRecord(
            event="provider_identification",
            message="Target provider identified",
            request_id=request_id,
            data={"provider": target_provider},
        )
    )

    logger.info(
        LogRecord(
            event="request_start",
            message="Request started",
            request_id=request_id,
            data={
                "client_model": anthropic_request.model,
                "target_model": target_model,
                "stream": is_stream,
            },
        )
    )

    logger.debug(
        LogRecord(
            event="request_body",
            message="Anthropic request body",
            request_id=request_id,
            data={"body": body},
        )
    )

    openai_messages = conversion.convert_anthropic_to_openai_messages(
        anthropic_request.messages, anthropic_request.system
    )
    openai_tools = conversion.convert_anthropic_tools_to_openai(anthropic_request.tools)
    openai_tool_choice = conversion.convert_anthropic_tool_choice_to_openai(
        anthropic_request.tool_choice
    )

    estimated_input_tokens = 0

    messages = cast(List[ChatCompletionMessageParam], openai_messages)
    tools = cast(Optional[List[ChatCompletionToolParam]], openai_tools)

    openai_params: Dict[str, Any] = {
        "model": target_model,
        "messages": messages,
        "max_tokens": anthropic_request.max_tokens,
        "stream": is_stream,
    }

    if anthropic_request.temperature is not None:
        openai_params["temperature"] = anthropic_request.temperature
    if anthropic_request.top_p is not None:
        openai_params["top_p"] = anthropic_request.top_p
    if anthropic_request.stop_sequences:
        openai_params["stop"] = anthropic_request.stop_sequences
    if tools:
        openai_params["tools"] = tools
    if openai_tool_choice is not None:
        openai_params["tool_choice"] = openai_tool_choice
    if anthropic_request.metadata and anthropic_request.metadata.get("user_id"):
        openai_params["user"] = str(anthropic_request.metadata.get("user_id"))

    logger.debug(
        LogRecord(
            event="openai_request",
            message="OpenAI request parameters",
            request_id=request_id,
            data={"params": openai_params},
        )
    )

    if is_stream:
        logger.debug(
            LogRecord(
                event="streaming_request",
                message="Initiating streaming request to OpenRouter",
                request_id=request_id,
            )
        )
        response_generator = await client.chat.completions.create(**openai_params)

        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            LogRecord(
                event="request_end",
                message="Streaming request completed",
                request_id=request_id,
                data={
                    "status_code": 200,
                    "duration_ms": duration_ms,
                    "input_tokens": estimated_input_tokens,
                    "output_tokens": "Streaming...",
                },
            )
        )

        return StreamingResponse(
            conversion.handle_streaming_response(
                response_generator,
                anthropic_request.model,
                estimated_input_tokens,
                request_id,
            ),
            media_type="text/event-stream",
        )
    else:
        logger.debug(
            LogRecord(
                event="non_streaming_request",
                message="Sending non-streaming request to OpenRouter",
                request_id=request_id,
            )
        )
        openai_response = await client.chat.completions.create(**openai_params)

        logger.debug(
            LogRecord(
                event="openai_response",
                message="OpenAI response received",
                request_id=request_id,
                data={"response": openai_response.model_dump()},
            )
        )

        anthropic_response = conversion.convert_openai_to_anthropic(
            openai_response, anthropic_request.model
        )
        usage_info = anthropic_response.usage.model_dump()

        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            LogRecord(
                event="request_end",
                message="Request completed successfully",
                request_id=request_id,
                data={
                    "status_code": 200,
                    "duration_ms": duration_ms,
                    "input_tokens": usage_info.get("input_tokens"),
                    "output_tokens": usage_info.get("output_tokens"),
                },
            )
        )

        logger.debug(
            LogRecord(
                event="anthropic_response",
                message="Anthropic response prepared",
                request_id=request_id,
                data={"response": anthropic_response.model_dump(exclude_unset=True)},
            )
        )

        return JSONResponse(content=anthropic_response.model_dump(exclude_unset=True))


@app.post(
    "/v1/messages/count_tokens",
    response_model=models.TokenCountResponse,
    tags=["Utility"],
)
async def count_tokens_endpoint(request: Request) -> models.TokenCountResponse:
    """
    Always returns 0 tokens. Token counting functionality has been disabled.
    """
    request_id = str(uuid.uuid4()).split("-")[0]
    request.state.request_id = request_id
    start_time = time.time()

    body = await request.json()

    models.TokenCountRequest.model_validate(body)

    duration_ms = (time.time() - start_time) * 1000
    logger.info(
        LogRecord(
            event="token_count",
            message="Token counting disabled - returning 0 tokens",
            request_id=request_id,
            data={"duration_ms": duration_ms},
        )
    )
    return models.TokenCountResponse(input_tokens=0)


@app.get("/", include_in_schema=False, tags=["Health"])
async def root() -> JSONResponse:
    """Basic health check and information endpoint."""
    logger.debug(
        LogRecord(event="health_check", message="Root health check endpoint accessed")
    )
    return JSONResponse(
        {"proxy": settings.app_name, "version": settings.app_version, "status": "ok"}
    )


def get_error_response(error_type: str, message: str) -> Dict[str, Any]:
    """Formats error response in Anthropic-compatible structure."""
    return {"type": "error", "error": {"type": error_type, "message": message}}


def extract_error_message(exc: Exception) -> str:
    """Extracts the most useful error message from various exception types."""
    if hasattr(exc, "body") and isinstance(exc.body, dict):
        error_details = exc.body.get("error", {})
        if isinstance(error_details, dict):
            message = error_details.get("message")
            if message is not None and isinstance(message, str):
                return message
            return str(exc)
        message = exc.body.get("message")
        if message is not None and isinstance(message, str):
            return message
        return str(exc)
    elif isinstance(exc, ValidationError):
        try:
            return json.dumps(exc.errors(), indent=2)
        except Exception:
            return str(exc)
    elif isinstance(exc, HTTPException):
        detail = exc.detail
        if detail is not None and isinstance(detail, str):
            return detail
        return str(detail)
    return str(exc)


async def _handle_error(
    request: Request, exc: Exception, status_code: int, anthropic_error_type: str
) -> JSONResponse:
    """Centralized logic for logging and formatting error responses."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()).split("-")[0])
    detail = extract_error_message(exc)

    duration = (
        (time.time() - request.state.start_time) * 1000
        if hasattr(request.state, "start_time")
        else 0
    )

    logger.log_exception(
        message=f"Request error: {detail}",
        exc=exc,
        request_id=request_id,
        event="request_error",
        data={
            "status_code": status_code,
            "duration_ms": duration,
            "error_type": anthropic_error_type,
        },
    )

    content = get_error_response(anthropic_error_type, detail)

    return JSONResponse(status_code=status_code, content=content)


@app.exception_handler(ValidationError)
async def validation_exception_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    """Handles Pydantic validation errors (422)."""
    return await _handle_error(request, exc, 422, "invalid_request_error")


@app.exception_handler(json.JSONDecodeError)
async def json_decode_exception_handler(
    request: Request, exc: json.JSONDecodeError
) -> JSONResponse:
    """Handles JSON parsing errors (400)."""
    detail = f"Invalid JSON format: {exc}"
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()).split("-")[0])

    logger.log_exception(
        message="Invalid JSON format in request",
        exc=exc,
        request_id=request_id,
        event="json_decode_error",
        data={"status_code": 400},
    )
    return JSONResponse(
        status_code=400, content=get_error_response("invalid_request_error", detail)
    )


@app.exception_handler(openai.APIError)
async def openai_api_error_handler(
    request: Request, exc: openai.APIError
) -> JSONResponse:
    """Handles all OpenAI API errors, mapping them to appropriate Anthropic types."""
    status_code = 500
    anthropic_error_type = "api_error"

    if isinstance(exc, openai.AuthenticationError):
        status_code = 401
        anthropic_error_type = "authentication_error"
    elif isinstance(exc, openai.RateLimitError):
        status_code = 429
        anthropic_error_type = "rate_limit_error"
    elif isinstance(exc, openai.BadRequestError):
        status_code = 400
        anthropic_error_type = "invalid_request_error"
    elif isinstance(exc, openai.PermissionDeniedError):
        status_code = 403
        anthropic_error_type = "permission_error"
    elif isinstance(exc, openai.NotFoundError):
        status_code = 404
        anthropic_error_type = "not_found_error"
    elif isinstance(exc, openai.UnprocessableEntityError):
        status_code = 422
        anthropic_error_type = "invalid_request_error"
    elif isinstance(exc, openai.InternalServerError):
        status_code = 500
        anthropic_error_type = "api_error"
    elif isinstance(exc, openai.APIConnectionError):
        status_code = 502
        anthropic_error_type = "api_error"
    elif isinstance(exc, openai.APITimeoutError):
        status_code = 504
        anthropic_error_type = "api_error"
    elif isinstance(exc, openai.APIStatusError):
        status_code = exc.status_code if hasattr(exc, "status_code") else 500
        error_type_mapping = {
            400: "invalid_request_error",
            401: "authentication_error",
            403: "permission_error",
            404: "not_found_error",
            413: "request_too_large",
            422: "invalid_request_error",
            429: "rate_limit_error",
            500: "api_error",
            502: "api_error",
            503: "overloaded_error",
            504: "api_error",
        }
        default_error = "api_error" if status_code >= 500 else "invalid_request_error"
        anthropic_error_type = error_type_mapping.get(status_code, default_error)

    return await _handle_error(request, exc, status_code, anthropic_error_type)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handles any other unexpected errors (500)."""
    return await _handle_error(request, exc, 500, "api_error")


@app.middleware("http")
async def add_process_time_header(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request.state.start_time = time.time()
    response = await call_next(request)
    return response
