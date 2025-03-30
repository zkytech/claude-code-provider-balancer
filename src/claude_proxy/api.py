"""
FastAPI application definition, endpoints, and request handling logic.
Orchestrates calls to other components (config, models, conversion, etc.).
"""
import fastapi
import json
import uuid
import time
import openai
import httpx
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from . import config
from .config import settings
from . import models
from . import conversion
from . import provider_mods
from . import token_counter
from .openrouter_client import client
from .logging_config import (
    logger,
    log_json_body,
    log_request_start,
    log_request_end,
    log_error_simplified,
)

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
    if (
        "opus" in client_model_lower or "sonnet" in client_model_lower
    ):
        target_model = settings.big_model_name
        logger.debug(
            f"ID: {request_id} Client model '{client_model_name}' mapped to BIG: {target_model}"
        )
    elif "haiku" in client_model_lower:
        target_model = settings.small_model_name
        logger.debug(
            f"ID: {request_id} Client model '{client_model_name}' mapped to SMALL: {target_model}"
        )
    else:
        target_model = settings.small_model_name
        logger.warning(
            f"ID: {request_id} Unknown client model '{client_model_name}'. Defaulting to SMALL: {target_model}"
        )
    return target_model




@app.post("/v1/messages", response_model=None, tags=["API"], status_code=200)
async def create_message(request: Request):
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
    logger.debug(f"ID: {request_id} Request body parsed and validated successfully.")

    target_model = select_target_model(anthropic_request.model, request_id)
    target_provider = target_model.split("/")[0].lower() if "/" in target_model else "unknown"
    logger.debug(f"ID: {request_id} Target provider identified as: {target_provider}")

    log_request_start(request_id, anthropic_request.model, target_model, is_stream)
    log_json_body("Anthropic Request Body", body, request_id, color="cyan")

    openai_messages = conversion.convert_anthropic_to_openai_messages(
        anthropic_request.messages, anthropic_request.system
    )
    openai_tools = conversion.convert_anthropic_tools_to_openai(
        anthropic_request.tools
    )
    openai_tool_choice = conversion.convert_anthropic_tool_choice_to_openai(
        anthropic_request.tool_choice
    )

    estimated_input_tokens = 0
    logger.debug(f"ID: {request_id} Token counting disabled - using 0 tokens")

    openai_params = {
        "model": target_model,
        "messages": openai_messages,
        "max_tokens": anthropic_request.max_tokens,
        **{
            k: v
            for k, v in {
                "temperature": anthropic_request.temperature,
                "top_p": anthropic_request.top_p,
                "stop": anthropic_request.stop_sequences,
                "stream": is_stream,
                "tools": openai_tools,
                "tool_choice": openai_tool_choice,
                "user": (
                    str(anthropic_request.metadata.get("user_id"))
                    if anthropic_request.metadata
                    else None
                ),
            }.items()
            if v is not None
        },
    }
    openai_params = {k: v for k, v in openai_params.items() if v is not None}

    modified_openai_params = provider_mods.apply_provider_modifications(
        openai_params, target_provider
    )
    log_json_body(
        "OpenAI Request Params (Modified)",
        modified_openai_params,
        request_id,
        color="magenta",
    )

    if is_stream:
        logger.debug(f"ID: {request_id} Initiating streaming request to OpenRouter.")
        response_generator = await client.chat.completions.create(**modified_openai_params)

        duration_ms = (time.time() - start_time) * 1000
        log_request_end(
            request_id,
            200,
            duration_ms,
            {
                "input_tokens": estimated_input_tokens,
                "output_tokens": "Streaming...",
            },
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
        logger.debug(f"ID: {request_id} Sending non-streaming request to OpenRouter.")
        openai_response = await client.chat.completions.create(**modified_openai_params)

        log_json_body(
            "OpenAI Response Body",
            openai_response.model_dump(),
            request_id,
            color="blue",
        )

        anthropic_response = conversion.convert_openai_to_anthropic(
            openai_response, anthropic_request.model
        )
        usage_info = anthropic_response.usage.model_dump()

        duration_ms = (time.time() - start_time) * 1000
        log_request_end(request_id, 200, duration_ms, usage_info)

        log_json_body(
            "Anthropic Response Body",
            anthropic_response.model_dump(exclude_unset=True),
            request_id,
            color="green",
        )

        return JSONResponse(content=anthropic_response.model_dump(exclude_unset=True))



@app.post(
    "/v1/messages/count_tokens",
    response_model=models.TokenCountResponse,
    tags=["Utility"],
)
async def count_tokens_endpoint(request: Request):
    """
    Always returns 0 tokens. Token counting functionality has been disabled.
    """
    request_id = str(uuid.uuid4()).split("-")[0]
    request.state.request_id = request_id
    start_time = time.time()

    body = await request.json()

    anthropic_request = models.TokenCountRequest.model_validate(body)

    duration_ms = (time.time() - start_time) * 1000
    logger.info(
        f"ID: {request_id} Token counting disabled - returning 0 tokens | Time: {duration_ms:.1f}ms"
    )
    return models.TokenCountResponse(input_tokens=0)


@app.get("/", include_in_schema=False, tags=["Health"])
async def root():
    """Basic health check and information endpoint."""
    logger.debug("Root health check endpoint accessed.")
    return JSONResponse(
        {"proxy": settings.app_name, "version": settings.app_version, "status": "ok"}
    )



def get_error_response(error_type: str, message: str) -> dict:
    """Formats error response in Anthropic-compatible structure."""
    return {
        "type": "error",
        "error": {
            "type": error_type,
            "message": message
        }
    }


def extract_error_message(exc: Exception) -> str:
    """Extracts the most useful error message from various exception types."""
    if hasattr(exc, 'body') and isinstance(exc.body, dict):
        error_details = exc.body.get('error', {})
        if isinstance(error_details, dict):
             return error_details.get('message', str(exc))
        return exc.body.get('message', str(exc))
    elif isinstance(exc, ValidationError):
         try:
             return json.dumps(exc.errors(), indent=2)
         except Exception:
             return str(exc)
    elif isinstance(exc, HTTPException):
        return str(exc.detail)
    return str(exc)


async def _handle_error(request: Request, exc: Exception, status_code: int, anthropic_error_type: str):
    """Centralized logic for logging and formatting error responses."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()).split("-")[0])
    detail = extract_error_message(exc)

    duration = (time.time() - request.state.start_time) * 1000 if hasattr(request.state, "start_time") else 0
    log_error_simplified(request_id, exc, status_code, duration, detail)

    content = get_error_response(anthropic_error_type, detail)

    return JSONResponse(
        status_code=status_code,
        content=content
    )


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """Handles Pydantic validation errors (422)."""
    return await _handle_error(request, exc, 422, "invalid_request_error")

@app.exception_handler(json.JSONDecodeError)
async def json_decode_exception_handler(request: Request, exc: json.JSONDecodeError):
    """Handles JSON parsing errors (400)."""
    detail = f"Invalid JSON format: {exc}"
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()).split("-")[0])
    log_error_simplified(request_id, exc, 400, 0, detail)
    return JSONResponse(
        status_code=400,
        content=get_error_response("invalid_request_error", detail)
    )

@app.exception_handler(openai.APIError)
async def openai_api_error_handler(request: Request, exc: openai.APIError):
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
        status_code = exc.status_code if hasattr(exc, 'status_code') else 500
        error_type_mapping = {
            400: "invalid_request_error", 401: "authentication_error",
            403: "permission_error", 404: "not_found_error",
            413: "request_too_large", 422: "invalid_request_error",
            429: "rate_limit_error", 500: "api_error",
            502: "api_error", 503: "overloaded_error", 504: "api_error"
        }
        default_error = "api_error" if status_code >= 500 else "invalid_request_error"
        anthropic_error_type = error_type_mapping.get(status_code, default_error)

    return await _handle_error(request, exc, status_code, anthropic_error_type)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handles any other unexpected errors (500)."""
    return await _handle_error(request, exc, 500, "api_error")


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    request.state.start_time = time.time()
    response = await call_next(request)
    return response
