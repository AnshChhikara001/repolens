from pathlib import Path

import pytest
from fakes import ScriptedChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

from repolens.config import DEFAULT_CHAT_MODEL, ModelConfigError, Settings
from repolens.costs import Price
from repolens.models import chat_model, price_table

pytestmark = pytest.mark.usefixtures("clean_env")


def test_default_model_is_gemini_flash() -> None:
    model = chat_model(Settings(google_api_key=SecretStr("g-key")))

    assert isinstance(model, ChatGoogleGenerativeAI)
    assert model.model == "gemini-3.5-flash"
    assert model.google_api_key == SecretStr("g-key")
    assert model.temperature == 0


def test_built_in_models_give_up_on_a_request_after_the_chat_timeout() -> None:
    model = chat_model(Settings(chat_timeout=30, google_api_key=SecretStr("k")))

    assert isinstance(model, ChatGoogleGenerativeAI)
    assert model.timeout == 30
    assert model.max_retries == 2


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


def test_a_model_without_a_price_is_refused() -> None:
    settings = Settings(chat_model="google_genai:gemini-1.0-pro", google_api_key=SecretStr("k"))

    with pytest.raises(ModelConfigError, match=r"google_genai:gemini-1\.0-pro in prices\.yaml"):
        chat_model(settings)


# A local models file that builds the scripted fake, so its calls are priced as `fake:scripted`.
LOCAL_MODELS = """
from fakes import ScriptedChatModel

PRICES = {"fake:scripted": {"input": 1.0, "output": 2.0, "free_tier": True}}


def chat_model(name, timeout):
    return ScriptedChatModel(script=[], name=f"{name} within {timeout}s")
"""


def test_a_local_model_is_built_by_the_local_models_file(tmp_path: Path) -> None:
    local_models = tmp_path / "models.py"
    local_models.write_text(LOCAL_MODELS)

    model = chat_model(Settings(chat_model="fake:scripted", local_models=local_models))

    assert isinstance(model, ScriptedChatModel)
    assert model.name == "fake:scripted within 120.0s"


def test_local_prices_are_added_to_the_bundled_ones(tmp_path: Path) -> None:
    local_models = tmp_path / "models.py"
    local_models.write_text(LOCAL_MODELS)

    prices = price_table(Settings(local_models=local_models))

    assert prices.require("fake:scripted") == Price(input=1.0, output=2.0, free_tier=True)
    assert prices.require(DEFAULT_CHAT_MODEL).free_tier


def test_without_local_models_the_bundled_prices_are_used() -> None:
    assert price_table(Settings()).require(DEFAULT_CHAT_MODEL).free_tier


def test_a_missing_local_models_file_is_named(tmp_path: Path) -> None:
    settings = Settings(chat_model="fake:scripted", local_models=tmp_path / "missing.py")

    with pytest.raises(ModelConfigError, match=r"LOCAL_MODELS file .*missing\.py not found"):
        chat_model(settings)


@pytest.mark.parametrize(
    "source",
    [
        "def chat_model(name, timeout): ...",
        "PRICES = {}",
        "PRICES = {'x:y': {'input': 'free'}}\ndef chat_model(name, timeout): ...",
        "PRICES = {}\nchat_model = 'not a function'",
    ],
)
def test_a_local_models_file_must_define_prices_and_a_factory(tmp_path: Path, source: str) -> None:
    local_models = tmp_path / "models.py"
    local_models.write_text(source)

    with pytest.raises(
        ModelConfigError, match=r"models\.py must define PRICES.* and chat_model\(name, timeout\)"
    ):
        chat_model(Settings(chat_model="fake:scripted", local_models=local_models))


def test_a_model_the_local_file_does_not_price_is_refused(tmp_path: Path) -> None:
    local_models = tmp_path / "models.py"
    local_models.write_text(LOCAL_MODELS)
    settings = Settings(chat_model="fake:other", local_models=local_models)

    with pytest.raises(ModelConfigError, match=r"'fake'.*or a model priced in LOCAL_MODELS"):
        chat_model(settings)


@pytest.mark.parametrize("source", ["def broken(:", "import no_such_package"])
def test_a_local_models_file_that_fails_to_load_is_named(tmp_path: Path, source: str) -> None:
    local_models = tmp_path / "models.py"
    local_models.write_text(source)

    with pytest.raises(ModelConfigError, match=r"LOCAL_MODELS file .*models\.py failed to load"):
        chat_model(Settings(chat_model="fake:scripted", local_models=local_models))


def test_a_local_file_cannot_reprice_a_bundled_model(tmp_path: Path) -> None:
    local_models = tmp_path / "models.py"
    local_models.write_text(
        f"PRICES = {{'{DEFAULT_CHAT_MODEL}': {{'input': 0, 'output': 0}}}}\n"
        "def chat_model(name, timeout): ..."
    )

    with pytest.raises(ModelConfigError, match=rf"{DEFAULT_CHAT_MODEL} is priced in prices\.yaml"):
        price_table(Settings(local_models=local_models))
