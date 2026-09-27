from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL = "postgresql://repolens:repolens@localhost:5432/repolens"
DEFAULT_CHAT_MODEL = "google_genai:gemini-3.5-flash"


class Settings(BaseSettings):
    """Runtime configuration, read from the environment and `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    database_url: str = DEFAULT_DATABASE_URL
    chat_model: str = DEFAULT_CHAT_MODEL
    google_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    github_token: SecretStr | None = None
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
