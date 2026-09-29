"""Chat models, chosen by configuration so a provider change is one setting (ADR-0003).

`CHAT_MODEL` is `provider:model`. Besides the built-in providers, `LOCAL_MODELS` can name a
Python file, kept out of the repository, that defines `llm(name, timeout)` and builds models
for any other provider.
"""

import importlib.util
from collections.abc import Callable
from functools import cache
from pathlib import Path

from repolens.config import ModelConfigError, Settings
from repolens.llm import LLM, AnthropicLLM, GeminiLLM

# Built-in providers, their adapter and the setting that holds their key.
PROVIDERS: dict[str, tuple[Callable[..., LLM], str]] = {
    "google": (GeminiLLM, "google_api_key"),
    "anthropic": (AnthropicLLM, "anthropic_api_key"),
}

type LocalFactory = Callable[[str, float], LLM]


def chat_provider(settings: Settings) -> str:
    """The provider part of `CHAT_MODEL`, e.g. `google`."""
    return settings.chat_model.partition(":")[0]


def build_llm(settings: Settings) -> LLM:
    """Build the chat model named by `CHAT_MODEL`."""
    provider = chat_provider(settings)
    model = settings.chat_model.partition(":")[2]
    if provider not in PROVIDERS:
        if settings.local_models is None:
            raise ModelConfigError(
                f"unsupported chat model {settings.chat_model!r}: use provider:model with one of"
                f" {', '.join(PROVIDERS)}, or set LOCAL_MODELS"
            )
        return load_local_models(settings.local_models)(settings.chat_model, settings.chat_timeout)
    adapter, key_setting = PROVIDERS[provider]
    key = getattr(settings, key_setting)
    if key is None:
        raise ModelConfigError(
            f"{key_setting.upper()} is not set (needed for {settings.chat_model})"
        )
    return adapter(model, api_key=key.get_secret_value(), timeout=settings.chat_timeout)


@cache
def load_local_models(path: Path) -> LocalFactory:
    """Run a `LOCAL_MODELS` file, once per process, and return its `llm` function."""
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
    factory: LocalFactory | None = getattr(module, "llm", None)
    if not callable(factory):
        raise ModelConfigError(f"{path} must define llm(name, timeout)")
    return factory
