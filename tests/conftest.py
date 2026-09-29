import os
from pathlib import Path

import psycopg
import pytest
from fakes import KeywordReranker, ScriptedLLM, fake_embedder, fixture_source
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from repolens import cli
from repolens.config import Settings
from repolens.store import ChunkStore

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://repolens:repolens@localhost:5432/repolens_test"
)


def create_database(url: str) -> None:
    name = str(conninfo_to_dict(url)["dbname"])
    with psycopg.connect(make_conninfo(url, dbname="postgres"), autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


@pytest.fixture
def store() -> ChunkStore:
    """An empty store in a separate test database. Skipped locally when Postgres is down."""
    try:
        create_database(TEST_DATABASE_URL)
    except psycopg.OperationalError as exc:
        if os.environ.get("CI"):
            raise
        pytest.skip(f"Postgres is not running: {exc}")
    store = ChunkStore(TEST_DATABASE_URL)
    store.setup()
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        conn.execute("TRUNCATE snapshots CASCADE")
    return store


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep the developer's shell and .env out of the tests."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Everything but the chat model: fixture repo, fake embeddings, test database."""
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("GOOGLE_API_KEY", "g-test")
    monkeypatch.setattr(cli, "GitHubSource", fixture_source)
    monkeypatch.setattr(cli, "OpenAIEmbedder", fake_embedder)
    monkeypatch.setattr(cli, "CrossEncoderReranker", KeywordReranker)


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch, offline: None) -> ScriptedLLM:
    model = ScriptedLLM()

    def scripted_model(settings: Settings) -> ScriptedLLM:
        return model

    monkeypatch.setattr(cli, "build_llm", scripted_model)
    return model
