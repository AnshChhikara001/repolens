from pathlib import Path

import pytest
from fakes import ScriptedLLM
from pydantic import SecretStr

from repolens.config import ModelConfigError, Settings
from repolens.llm import AnthropicLLM, GeminiLLM
from repolens.models import build_llm

pytestmark = pytest.mark.usefixtures("clean_env")


def test_default_model_is_gemini_flash_lite() -> None:
    model = build_llm(Settings(google_api_key=SecretStr("g-key")))

    assert isinstance(model, GeminiLLM)
    assert model.name == "google:gemini-3.1-flash-lite"


def test_model_is_chosen_by_config() -> None:
    settings = Settings(chat_model="anthropic:claude-sonnet-5", anthropic_api_key=SecretStr("k"))

    model = build_llm(settings)

    assert isinstance(model, AnthropicLLM)
    assert model.name == "anthropic:claude-sonnet-5"


@pytest.mark.parametrize(
    ("chat_model", "key"),
    [
        ("google:gemini-3.1-flash-lite", "GOOGLE_API_KEY"),
        ("anthropic:claude-x", "ANTHROPIC_API_KEY"),
    ],
)
def test_missing_provider_key_is_named(chat_model: str, key: str) -> None:
    with pytest.raises(ModelConfigError, match=f"{key} is not set"):
        build_llm(Settings(chat_model=chat_model))


@pytest.mark.parametrize("chat_model", ["acme:big-model", "no-provider"])
def test_unknown_provider_is_rejected(chat_model: str) -> None:
    with pytest.raises(ModelConfigError, match=r"unsupported chat model .*google, anthropic"):
        build_llm(Settings(chat_model=chat_model))


# A local models file that builds the scripted fake and says how it was asked for.
LOCAL_MODELS = """
from fakes import ScriptedLLM


def llm(name, timeout):
    model = ScriptedLLM()
    model.name = f"{name} within {timeout}s"
    return model
"""


def local_models(tmp_path: Path, source: str = LOCAL_MODELS) -> Path:
    path = tmp_path / "models.py"
    path.write_text(source)
    return path


def test_other_providers_are_built_by_the_local_models_file(tmp_path: Path) -> None:
    settings = Settings(chat_model="fake:scripted", local_models=local_models(tmp_path))

    model = build_llm(settings)

    assert isinstance(model, ScriptedLLM)
    assert model.name == "fake:scripted within 120.0s"


def test_built_in_providers_do_not_need_the_local_models_file(tmp_path: Path) -> None:
    settings = Settings(google_api_key=SecretStr("k"), local_models=local_models(tmp_path))

    assert isinstance(build_llm(settings), GeminiLLM)


def test_a_missing_local_models_file_is_named(tmp_path: Path) -> None:
    settings = Settings(chat_model="fake:scripted", local_models=tmp_path / "missing.py")

    with pytest.raises(ModelConfigError, match=r"LOCAL_MODELS file .*missing\.py not found"):
        build_llm(settings)


@pytest.mark.parametrize("source", ["", "llm = 'not a function'"])
def test_a_local_models_file_must_define_llm(tmp_path: Path, source: str) -> None:
    settings = Settings(chat_model="fake:scripted", local_models=local_models(tmp_path, source))

    with pytest.raises(ModelConfigError, match=r"models\.py must define llm\(name, timeout\)"):
        build_llm(settings)


@pytest.mark.parametrize("source", ["def broken(:", "import no_such_package"])
def test_a_local_models_file_that_fails_to_load_is_named(tmp_path: Path, source: str) -> None:
    settings = Settings(chat_model="fake:scripted", local_models=local_models(tmp_path, source))

    with pytest.raises(ModelConfigError, match=r"LOCAL_MODELS file .*models\.py failed to load"):
        build_llm(settings)
