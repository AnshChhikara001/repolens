"""Chat models, chosen by configuration so a provider change is one setting (ADR-0003)."""

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from repolens.config import Settings

# Providers we hold a key for, and the setting that holds it.
API_KEYS = {
    "google_genai": "google_api_key",
    "groq": "groq_api_key",
    "openai": "openai_api_key",
}


class ModelConfigError(Exception):
    """The configured chat model can't be used."""


def chat_model(settings: Settings) -> BaseChatModel:
    """Build the chat model named by `CHAT_MODEL`, written `provider:model`."""
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
    return init_chat_model(settings.chat_model, api_key=key.get_secret_value(), temperature=0)
