from pathlib import Path

import pytest
from pydantic import SecretStr
from typer.testing import CliRunner

from repolens.cli import app
from repolens.config import Settings
from repolens.doctor import Check, DatabaseUnavailable, healthy, probe_database, run_checks

runner = CliRunner()

CLOSED_PORT_URL = "postgresql://repolens:repolens@127.0.0.1:1/repolens"
ENV_VARS = (
    "DATABASE_URL",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "GITHUB_TOKEN",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "OPENAI_API_KEY",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep the developer's shell and .env out of the tests."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def reachable(_url: str) -> str:
    return "pgvector 0.8.0"


def unreachable(_url: str) -> str:
    raise DatabaseUnavailable("connection refused")


def check_named(checks: list[Check], name: str) -> Check:
    return next(check for check in checks if check.name == name)


def test_healthy_with_database_and_required_key() -> None:
    checks = run_checks(Settings(google_api_key=SecretStr("g-key")), reachable)

    assert healthy(checks)
    assert "pgvector 0.8.0" in check_named(checks, "database").detail


def test_unreachable_database_is_unhealthy() -> None:
    checks = run_checks(Settings(google_api_key=SecretStr("g-key")), unreachable)

    database = check_named(checks, "database")
    assert not healthy(checks)
    assert not database.ok
    assert "connection refused" in database.detail


def test_missing_required_key_is_unhealthy() -> None:
    checks = run_checks(Settings(), reachable)

    assert not healthy(checks)
    assert not check_named(checks, "GOOGLE_API_KEY").ok


def test_missing_optional_keys_are_reported_but_healthy() -> None:
    checks = run_checks(Settings(google_api_key=SecretStr("g-key")), reachable)

    groq = check_named(checks, "GROQ_API_KEY")
    assert healthy(checks)
    assert not groq.ok
    assert not groq.required


def test_empty_key_in_env_file_counts_as_missing(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("GOOGLE_API_KEY=\nGROQ_API_KEY=q-key\n")

    checks = run_checks(Settings(), reachable)

    assert not check_named(checks, "GOOGLE_API_KEY").ok
    assert check_named(checks, "GROQ_API_KEY").ok


def test_probe_raises_when_database_is_down() -> None:
    with pytest.raises(DatabaseUnavailable):
        probe_database(CLOSED_PORT_URL)


def test_doctor_command_reports_status_and_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", CLOSED_PORT_URL)
    monkeypatch.setenv("GOOGLE_API_KEY", "g-key")

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "database" in result.output
    assert "GOOGLE_API_KEY" in result.output
    assert "g-key" not in result.output
