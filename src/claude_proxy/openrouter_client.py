"""
Initializes and configures the OpenAI AsyncClient for interacting with OpenRouter.
"""

import openai

from .config import settings
from .logging_config import logger

client = openai.AsyncClient(
    api_key=settings.openrouter_api_key,
    base_url=settings.openrouter_base_url,
    default_headers={
        "HTTP-Referer": settings.referrer_url,
        "X-Title": settings.app_name,
    },
)

logger.info("OpenAI AsyncClient initialized for OpenRouter.")
