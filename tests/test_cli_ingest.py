from pathlib import Path

import pytest
from conftest import TEST_DATABASE_URL
from fakes import SHA, FakeEmbedder, FixtureSource
from typer.testing import CliRunner

from repolens import cli
from repolens.store import ChunkStore

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep the developer's shell and .env out of the tests."""
    for name in ("DATABASE_URL", "OPENAI_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def fixture_source(token: str | None) -> FixtureSource:
    return FixtureSource()


def fake_embedder(api_key: str) -> FakeEmbedder:
    return FakeEmbedder()


def test_ingest_prints_the_snapshot_and_chunk_count(
    store: ChunkStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(cli, "GitHubSource", fixture_source)
    monkeypatch.setattr(cli, "OpenAIEmbedder", fake_embedder)

    first = runner.invoke(cli.app, ["ingest", "acme/shop@main"])
    second = runner.invoke(cli.app, ["ingest", "acme/shop@main"])

    assert first.exit_code == 0
    assert first.output == f"Ingested acme/shop@{SHA}: 6 chunks from 4 files\n"
    assert second.output == f"Already ingested acme/shop@{SHA}: 6 chunks from 4 files\n"


def test_ingest_needs_an_openai_key() -> None:
    result = runner.invoke(cli.app, ["ingest", "acme/shop"])

    assert result.exit_code == 1
    assert "OPENAI_API_KEY" in result.output


def test_ingest_rejects_a_malformed_repo() -> None:
    result = runner.invoke(cli.app, ["ingest", "not-a-repo"])

    assert result.exit_code == 2
    assert "owner/repo" in result.output
