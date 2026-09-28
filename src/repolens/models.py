"""Chat models, chosen by configuration so a provider change is one setting (ADR-0003)."""

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from repolens.config import ModelConfigError, Settings
from repolens.costs import load_prices

# Providers we hold a key for, and the setting that holds it.
API_KEYS = {
    "google_genai": "google_api_key",
    "groq": "groq_api_key",
    "openai": "openai_api_key",
}

# Each retry may wait the full CHAT_TIMEOUT, so keep them few.
MAX_RETRIES = 2


def chat_model(settings: Settings) -> BaseChatModel:
    """Build the chat model named by `CHAT_MODEL`, written `provider:model`.

    Every call is priced (ADR-0004), so a model must be in the price table.
    """
    provider = settings.chat_model.partition(":")[0]
    if provider not in API_KEYS:
        raise ModelConfigError(
            f"unsupported chat model provider {provider!r}, use one of {', '.join(API_KEYS)}"
        )
    key = getattr(settings, API_KEYS[provider])
    if key is None:
        raise ModelConfigError(
            f"{API_KEYS[provider].upper()} is not set (needed for {settings.chat_model})"
        )
    load_prices().require(settings.chat_model)
    return init_chat_model(
        settings.chat_model,
        api_key=key.get_secret_value(),
        temperature=0,
        timeout=settings.chat_timeout,
        max_retries=MAX_RETRIES,
    )
