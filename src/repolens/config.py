from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL = "postgresql://repolens:repolens@localhost:5432/repolens"
DEFAULT_CHAT_MODEL = "google:gemini-3.1-flash-lite"
DEFAULT_CHAT_TIMEOUT = 120.0
DEFAULT_RUNS_DIR = Path.home() / ".repolens" / "runs"


class Settings(BaseSettings):
    """Runtime configuration, read from the environment and `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    database_url: str = DEFAULT_DATABASE_URL
    chat_model: str = DEFAULT_CHAT_MODEL
    chat_timeout: float = DEFAULT_CHAT_TIMEOUT
    local_models: Path | None = None
    runs_dir: Path = DEFAULT_RUNS_DIR
    google_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    github_token: SecretStr | None = None


class ModelConfigError(Exception):
    """The configured chat model can't be used."""
