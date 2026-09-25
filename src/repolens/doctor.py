from collections.abc import Callable
from dataclasses import dataclass

import psycopg
from pydantic import SecretStr

from repolens.config import Settings


class DatabaseUnavailable(Exception):
    """The database can't be reached or is missing pgvector."""


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def probe_database(url: str) -> str:
    """Connect to Postgres and return the installed pgvector version."""
    try:
        with psycopg.connect(url, connect_timeout=3) as conn:
            row = conn.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            ).fetchone()
    except psycopg.Error as exc:
        message = str(exc).strip() or type(exc).__name__
        raise DatabaseUnavailable(message.splitlines()[0]) from exc
    if row is None:
        raise DatabaseUnavailable("pgvector extension is not installed")
    return f"pgvector {row[0]}"


def run_checks(settings: Settings, probe: Callable[[str], str]) -> list[Check]:
    """Check the database and each configured API key."""
    try:
        database = Check("database", True, probe(settings.database_url))
    except DatabaseUnavailable as exc:
        database = Check("database", False, str(exc))

    keys: list[tuple[str, SecretStr | None, str, bool]] = [
        ("GOOGLE_API_KEY", settings.google_api_key, "Gemini chat models", True),
        ("GROQ_API_KEY", settings.groq_api_key, "Groq fallback models", False),
        ("GITHUB_TOKEN", settings.github_token, "higher GitHub API rate limits", False),
        ("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key, "Langfuse tracing", False),
        ("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key, "Langfuse tracing", False),
        ("OPENAI_API_KEY", settings.openai_api_key, "eval comparison only", False),
    ]
    return [database] + [
        Check(name, value is not None, purpose, required) for name, value, purpose, required in keys
    ]


def healthy(checks: list[Check]) -> bool:
    return all(check.ok for check in checks if check.required)
