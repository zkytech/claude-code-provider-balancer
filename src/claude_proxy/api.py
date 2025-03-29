# -*- coding: utf-8 -*-
"""
FastAPI application definition, endpoints, and request handling logic.
Orchestrates calls to other components (config, models, conversion, etc.).
"""
import fastapi
import json
import uuid
import time
import openai  # For exception types
from httpx import ReadError, ConnectError, ConnectTimeout
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

# --- Relative Imports for Internal Components ---
from . import config
from .config import settings
from . import models
from . import conversion
from . import provider_mods
from . import token_counter
from .openrouter_client import client  # Import the initialized client instance
from .logging_config import (
    logger,
    log_json_body,
    log_request_start,
    log_request_end,
    log_error_simplified,
)

# --- FastAPI Application Setup ---
app = fastapi.FastAPI(
    title=settings.app_name,
    description="Routes Anthropic API requests to OpenRouter, selecting models dynamically.",
    version=settings.app_version,
    docs_url=None,  # Disable default docs
    redoc_url=None,  # Disable default ReDoc
)


# --- Helper Function for Model Selection ---
def select_target_model(client_model_name: str, request_id: str) -> str:
    """Selects the target OpenRouter model based on the client's request."""
    client_model_lower = client_model_name.lower()
    # Prioritize specific keywords for big model
    if (
        "opus" in client_model_lower or "sonnet" in client_model_lower
    ):  # Add sonnet here too
        target_model = settings.big_model_name
        logger.debug(
            f"ID: {request_id} Client model '{client_model_name}' mapped to BIG: {target_model}"
        )
    elif "haiku" in client_model_lower:  # Specific keyword for small model
        target_model = settings.small_model_name
        logger.debug(
            f"ID: {request_id} Client model '{client_model_name}' mapped to SMALL: {target_model}"
        )
    else:
        # Default to small model for unrecognized names
        target_model = settings.small_model_name
        logger.warning(
            f"ID: {request_id} Unknown client model '{client_model_name}'. Defaulting to SMALL: {target_model}"
        )
    return target_model


# --- API Endpoints ---


@app.post("/v1/messages", response_model=None, tags=["API"], status_code=200)
async def create_message(request: Request):
    """
    Main endpoint for Anthropic message completions, proxied to OpenRouter.
    Handles conversions, streaming, dynamic model selection, and provider mods.
    Logs requests and errors with traceable IDs.
    """
    start_time = time.time()
    request_id = str(uuid.uuid4()).split("-")[0]  # Short UUID for request ID
    target_model: str | None = None  # Initialize
    status_code = 500  # Default to internal error
    detail = "Internal Server Error"
    exc_info: Exception | None = None  # Store exception for logging
    usage_info: dict | None = None
    is_stream = False  # Default to non-streaming

    try:
        # 1. Parse Request Body & Validate
        try:
            body = await request.json()
            # Validate against the Pydantic model
            anthropic_request = models.MessagesRequest.model_validate(body)
            is_stream = (
                anthropic_request.stream or False
            )  # Determine stream status early
            logger.debug(
                f"ID: {request_id} Request body parsed and validated successfully."
            )
        except json.JSONDecodeError as e:
            status_code, detail, exc_info = 400, f"Invalid JSON format: {e}", e
            # Log before raising to capture request ID
            log_error_simplified(
                request_id, e, status_code, (time.time() - start_time) * 1000, detail
            )
            raise HTTPException(status_code=status_code, detail=detail) from e
        except ValidationError as e:
            status_code, detail, exc_info = 422, f"Invalid Request Body: {e}", e
            log_error_simplified(
                request_id, e, status_code, (time.time() - start_time) * 1000, detail
            )
            raise HTTPException(status_code=status_code, detail=detail) from e
        except Exception as e:  # Catch unexpected parsing errors
            status_code, detail, exc_info = (
                400,
                f"Error processing request body: {e}",
                e,
            )
            log_error_simplified(
                request_id, e, status_code, (time.time() - start_time) * 1000, detail
            )
            raise HTTPException(status_code=status_code, detail=detail) from e

        # 2. Dynamic Model Selection & Provider Identification
        target_model = select_target_model(anthropic_request.model, request_id)
        # Infer provider from model name (e.g., "google/gemini-pro" -> "google")
        target_provider = (
            target_model.split("/")[0].lower() if "/" in target_model else "unknown"
        )
        logger.debug(
            f"ID: {request_id} Target provider identified as: {target_provider}"
        )

        # Log request start details
        log_request_start(request_id, anthropic_request.model, target_model, is_stream)
        log_json_body("Anthropic Request Body", body, request_id, color="cyan")

        # 3. Convert Anthropic Request -> OpenAI Format
        openai_messages = conversion.convert_anthropic_to_openai_messages(
            anthropic_request.messages, anthropic_request.system
        )
        openai_tools = conversion.convert_anthropic_tools_to_openai(
            anthropic_request.tools
        )
        openai_tool_choice = conversion.convert_anthropic_tool_choice_to_openai(
            anthropic_request.tool_choice
        )

        # Estimate input tokens *after* conversion
        estimated_input_tokens = token_counter.count_tokens_for_request(
            messages=anthropic_request.messages,  # Use original for consistency if needed
            system=anthropic_request.system,
            model_name=target_model,  # Use target model for encoding
        )
        logger.debug(
            f"ID: {request_id} Estimated input tokens: {estimated_input_tokens}"
        )

        # 4. Assemble OpenAI API Parameters
        openai_params = {
            "model": target_model,
            "messages": openai_messages,
            "max_tokens": anthropic_request.max_tokens,
            # Include optional parameters only if they are not None
            **{
                k: v
                for k, v in {
                    "temperature": anthropic_request.temperature,
                    "top_p": anthropic_request.top_p,
                    # top_k is ignored by OpenAI but included here if needed elsewhere
                    # "top_k": anthropic_request.top_k,
                    "stop": anthropic_request.stop_sequences,
                    "stream": is_stream,
                    "tools": openai_tools,
                    "tool_choice": openai_tool_choice,
                    # Map metadata.user_id to OpenAI's 'user' parameter
                    "user": (
                        str(anthropic_request.metadata.get("user_id"))
                        if anthropic_request.metadata
                        else None
                    ),
                }.items()
                if v is not None
            },
        }
        # Clean params again to remove any keys added with None values
        openai_params = {k: v for k, v in openai_params.items() if v is not None}

        # 5. Apply Provider-Specific Modifications
        modified_openai_params = provider_mods.apply_provider_modifications(
            openai_params, target_provider
        )
        log_json_body(
            "OpenAI Request Params (Modified)",
            modified_openai_params,
            request_id,
            color="magenta",
        )

        # 6. Call OpenRouter API (Streaming or Non-Streaming)
        if is_stream:
            # --- Streaming Response ---
            logger.debug(
                f"ID: {request_id} Initiating streaming request to OpenRouter."
            )
            response_generator = await client.chat.completions.create(
                **modified_openai_params
            )
            status_code = 200  # Mark as success for starting the stream
            # Log stream initiation success *before* returning the response
            duration_ms = (time.time() - start_time) * 1000
            log_request_end(
                request_id,
                status_code,
                duration_ms,
                {
                    "input_tokens": estimated_input_tokens,
                    "output_tokens": "Streaming...",
                },
            )

            # Return the streaming response using the conversion generator
            return StreamingResponse(
                conversion.handle_streaming_response(
                    response_generator,
                    anthropic_request.model,  # Pass original model name back
                    estimated_input_tokens,
                    request_id,  # Pass request ID for logging within stream handler
                ),
                media_type="text/event-stream",
            )
        else:
            # --- Non-Streaming Response ---
            logger.debug(
                f"ID: {request_id} Sending non-streaming request to OpenRouter."
            )
            openai_response = await client.chat.completions.create(
                **modified_openai_params
            )
            log_json_body(
                "OpenAI Response Body",
                openai_response.model_dump(),
                request_id,
                color="blue",
            )

            # 7. Convert OpenAI Response -> Anthropic Format
            anthropic_response = conversion.convert_openai_to_anthropic(
                openai_response, anthropic_request.model  # Pass original model name
            )
            status_code = 200  # Mark as success
            usage_info = anthropic_response.usage.model_dump()  # Get usage info
            log_json_body(
                "Anthropic Response Body",
                anthropic_response.model_dump(exclude_unset=True),
                request_id,
                color="green",
            )

            # Return the converted response
            return JSONResponse(
                content=anthropic_response.model_dump(exclude_unset=True)
            )

    # --- Centralized Error Handling ---
    # Catch specific OpenAI/HTTPX errors first, then general exceptions
    except openai.AuthenticationError as e:
        status_code, detail, exc_info = (
            401,
            f"OpenRouter Authentication Error: {e.body.get('message', e) if e.body else e}",
            e,
        )
    except openai.RateLimitError as e:
        status_code, detail, exc_info = (
            429,
            f"OpenRouter Rate Limit Error: {e.body.get('message', e) if e.body else e}",
            e,
        )
    except openai.BadRequestError as e:
        # Often indicates an issue with the request structure after conversion/modification
        status_code, detail, exc_info = (
            400,
            f"OpenRouter Bad Request Error: {e.body.get('message', e) if e.body else e}",
            e,
        )
        log_json_body(
            "Failed OpenAI Request Params",
            (
                modified_openai_params
                if "modified_openai_params" in locals()
                else openai_params if "openai_params" in locals() else body
            ),
            request_id,
            color="red",
        )  # Log params that caused error
    except (openai.APIConnectionError, ConnectError, ConnectTimeout, ReadError) as e:
        status_code, detail, exc_info = 502, f"Connection Error to OpenRouter: {e}", e
    except openai.InternalServerError as e:
        status_code, detail, exc_info = (
            500,
            f"OpenRouter Internal Server Error: {e.body.get('message', e) if e.body else e}",
            e,
        )
    except openai.APIStatusError as e:  # Catch other non-2xx responses from OpenRouter
        status_code, detail, exc_info = (
            e.status_code,
            f"OpenRouter API Error ({e.status_code}): {e.body.get('message', e) if e.body else e}",
            e,
        )
    except HTTPException as e:
        # Re-catch HTTPException to ensure logging happens, but keep original status/detail
        status_code, detail, exc_info = e.status_code, str(e.detail), e
        # Error should have been logged before raising in parsing/validation
    except Exception as e:
        # Catch any other unexpected errors
        status_code, detail, exc_info = 500, f"Unexpected Internal Server Error: {e}", e
    finally:
        # --- Final Logging ---
        # Log end/error details unless it was a successfully initiated stream
        # (stream success is logged before returning the StreamingResponse)
        if not (is_stream and status_code == 200):
            duration_ms = (time.time() - start_time) * 1000
            if status_code == 200:
                # Log successful non-streaming request end
                log_request_end(request_id, status_code, duration_ms, usage_info)
            elif exc_info:
                # Log error using the simplified helper
                log_error_simplified(
                    request_id, exc_info, status_code, duration_ms, detail
                )
            else:
                # Log non-200 status without a specific exception (should be rare)
                log_request_end(
                    request_id, status_code, duration_ms
                )  # No usage info on error

    # If an error occurred and we didn't return a response/stream, raise HTTPException
    if status_code != 200:
        # Ensure detail is a string
        detail_str = (
            str(detail) if detail is not None else "An unexpected error occurred."
        )
        # Avoid raising again if it was already an HTTPException caught above
        if not isinstance(exc_info, HTTPException):
            raise HTTPException(status_code=status_code, detail=detail_str)
        # If it *was* an HTTPException, it was already raised, so we just exit the function


@app.post(
    "/v1/messages/count_tokens",
    response_model=models.TokenCountResponse,
    tags=["Utility"],
)
async def count_tokens_endpoint(request: Request):
    """
    Estimates token count for a given Anthropic payload using tiktoken,
    based on the target model that *would* be selected.
    """
    request_id = str(uuid.uuid4()).split("-")[0]
    start_time = time.time()
    status_code = 500
    detail = "Error counting tokens"
    exc_info: Exception | None = None

    try:
        # 1. Parse and Validate Request
        try:
            body = await request.json()
            anthropic_request = models.TokenCountRequest.model_validate(body)
        except json.JSONDecodeError as e:
            status_code, detail, exc_info = 400, f"Invalid JSON: {e}", e
            raise HTTPException(status_code=status_code, detail=detail) from e
        except ValidationError as e:
            status_code, detail, exc_info = 422, f"Invalid Request Body: {e}", e
            raise HTTPException(status_code=status_code, detail=detail) from e

        # 2. Select Target Model (same logic as /v1/messages)
        target_model = select_target_model(anthropic_request.model, request_id)

        # 3. Perform Token Count
        token_count = token_counter.count_tokens_for_request(
            messages=anthropic_request.messages,
            system=anthropic_request.system,
            model_name=target_model,  # Use the determined target model
            tools=anthropic_request.tools,  # Pass tools if needed by counter in future
        )
        status_code = 200  # Success

        # 4. Log and Return Result
        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            f"ID: {request_id} Count Tokens ≈ {token_count} (Client: {anthropic_request.model}, TargetEst: {target_model}) | Time: {duration_ms:.1f}ms"
        )
        return models.TokenCountResponse(input_tokens=token_count)

    except HTTPException as e:
        # Capture details if raised during parsing/validation
        status_code, detail, exc_info = e.status_code, str(e.detail), e
        # Log here as it wasn't logged before raising in this endpoint
        log_error_simplified(
            request_id, e, status_code, (time.time() - start_time) * 1000, detail
        )
        raise  # Re-raise the captured HTTPException
    except Exception as e:
        status_code, detail, exc_info = (
            500,
            f"Unexpected error during token counting: {e}",
            e,
        )
        # Log the unexpected error
        log_error_simplified(
            request_id, e, status_code, (time.time() - start_time) * 1000, detail
        )
        raise HTTPException(status_code=status_code, detail=detail) from e


@app.get("/", include_in_schema=False, tags=["Health"])
async def root():
    """Basic health check and information endpoint."""
    logger.debug("Root health check endpoint accessed.")
    return JSONResponse(
        {"proxy": settings.app_name, "version": settings.app_version, "status": "ok"}
    )


# --- Optional: Add Exception Handlers for Cleaner Code ---
# Example:
# @app.exception_handler(RequestValidationError)
# async def validation_exception_handler(request: Request, exc: RequestValidationError):
#     # Log error, return 422
#     pass
#
# @app.exception_handler(StarletteHTTPException)
# async def http_exception_handler(request: Request, exc: StarletteHTTPException):
#     # Log error, return original status code and detail
#     pass
#
# @app.exception_handler(Exception)
# async def generic_exception_handler(request: Request, exc: Exception):
#     # Log error, return 500
#     pass
