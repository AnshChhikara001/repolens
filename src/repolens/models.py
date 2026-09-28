"""Chat models, chosen by configuration so a provider change is one setting (ADR-0003).

Besides the built-in providers, `LOCAL_MODELS` can name a Python file of extra ones kept out
of the repository. The file defines `PRICES`, keyed `provider:model` like `prices.yaml`, and
`chat_model(name, timeout)`, which builds any model it prices. Calls are priced by the
provider and model name the built model reports to LangChain, so they must match its key.
"""

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from pydantic import TypeAdapter, ValidationError

from repolens.config import ModelConfigError, Settings
from repolens.costs import Price, PriceTable, load_prices

# Providers we hold a key for, and the setting that holds it.
API_KEYS = {
    "google_genai": "google_api_key",
    "groq": "groq_api_key",
    "openai": "openai_api_key",
}

# Each retry may wait the full CHAT_TIMEOUT, so keep them few.
MAX_RETRIES = 2


@dataclass(frozen=True)
class LocalModels:
    """The chat models a `LOCAL_MODELS` file adds."""

    prices: dict[str, Price]
    chat_model: Callable[[str, float], BaseChatModel]


def chat_model(settings: Settings) -> BaseChatModel:
    """Build the chat model named by `CHAT_MODEL`, written `provider:model`.

    Every call is priced (ADR-0004), so a model must be in the price table.
    """
    if settings.local_models is not None:
        local = load_local_models(settings.local_models)
        if settings.chat_model in local.prices:
            return local.chat_model(settings.chat_model, settings.chat_timeout)
    provider = settings.chat_model.partition(":")[0]
    if provider not in API_KEYS:
        raise ModelConfigError(
            f"unsupported chat model provider {provider!r}, use one of {', '.join(API_KEYS)}"
            " or a model priced in LOCAL_MODELS"
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


def price_table(settings: Settings) -> PriceTable:
    """The bundled prices, plus those of the `LOCAL_MODELS` file if there is one."""
    prices = load_prices()
    if settings.local_models is None:
        return prices
    return prices.merged(load_local_models(settings.local_models).prices)


@cache
def load_local_models(path: Path) -> LocalModels:
    """Run a `LOCAL_MODELS` file, once per process, and read the models it adds."""
    if not path.is_file():
        raise ModelConfigError(f"LOCAL_MODELS file {path} not found")
    spec = importlib.util.spec_from_file_location("repolens_local_models", path)
    if spec is None or spec.loader is None:
        raise ModelConfigError(f"LOCAL_MODELS file {path} is not a Python file")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise ModelConfigError(f"LOCAL_MODELS file {path} failed to load: {exc!r}") from exc
    factory: Callable[[str, float], BaseChatModel] | None = getattr(module, "chat_model", None)
    try:
        prices = TypeAdapter(dict[str, Price]).validate_python(getattr(module, "PRICES", None))
    except ValidationError:
        prices = None
    if prices is None or not callable(factory):
        raise ModelConfigError(
            f"{path} must define PRICES, as prices.yaml's models, and chat_model(name, timeout)"
        )
    return LocalModels(prices, factory)
