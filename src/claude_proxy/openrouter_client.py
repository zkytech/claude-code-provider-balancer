# -*- coding: utf-8 -*-
"""
Initializes and configures the OpenAI AsyncClient for interacting with OpenRouter.
"""
import openai
from .config import settings
from .logging_config import logger  # Import the logger

# --- OpenAI Client Setup ---
# Initialize the client instance once when the module is imported.
# This instance will be reused across requests.
client = openai.AsyncClient(
    api_key=settings.openrouter_api_key,
    base_url=settings.openrouter_base_url,
    # Set default headers required by OpenRouter
    default_headers={
        "HTTP-Referer": settings.referrer_url,
        "X-Title": settings.app_name,
    },
    # Optional: Configure timeouts (example)
    # timeout=httpx.Timeout(60.0, connect=5.0)
)

logger.info(
    "OpenAI AsyncClient initialized for OpenRouter."
)  # Use logger from logging_config

# You can add functions here if needed, e.g., to get the client instance explicitly,
# but simply importing `client` from this module is the common pattern.
# def get_client() -> openai.AsyncClient:
#     return client
