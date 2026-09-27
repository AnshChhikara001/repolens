import pytest
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

from repolens.config import Settings
from repolens.models import ModelConfigError, chat_model

pytestmark = pytest.mark.usefixtures("clean_env")


def test_default_model_is_gemini_flash() -> None:
    model = chat_model(Settings(google_api_key=SecretStr("g-key")))

    assert isinstance(model, ChatGoogleGenerativeAI)
    assert model.model == "gemini-3.5-flash"
    assert model.google_api_key == SecretStr("g-key")
    assert model.temperature == 0


def test_model_is_chosen_by_config() -> None:
    model = chat_model(
        Settings(chat_model="google_genai:gemini-3.5-flash-lite", google_api_key=SecretStr("k"))
    )

    assert isinstance(model, ChatGoogleGenerativeAI)
    assert model.model == "gemini-3.5-flash-lite"


def test_missing_provider_key_is_named() -> None:
    with pytest.raises(ModelConfigError, match="GROQ_API_KEY"):
        chat_model(Settings(chat_model="groq:llama-3.3-70b", google_api_key=SecretStr("k")))


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(ModelConfigError, match="'acme'"):
        chat_model(Settings(chat_model="acme:big-model"))
