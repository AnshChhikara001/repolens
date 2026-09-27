import pytest
from conftest import TEST_DATABASE_URL
from fakes import (
    CALL_COST,
    FAKE_PRICES,
    SHA,
    KeywordReranker,
    ScriptedChatModel,
    fake_embedder,
    fixture_source,
)
from typer.testing import CliRunner

from repolens import cli
from repolens.code_navigator import CodeFindings
from repolens.config import Settings
from repolens.costs import PriceTable
from repolens.ledger import Ledger
from repolens.report import Citation, Finding
from repolens.report_writer import ReportDraft
from repolens.store import ChunkStore

runner = CliRunner()
pytestmark = pytest.mark.usefixtures("clean_env")

FINDINGS = CodeFindings(
    findings=[
        Finding(
            claim="Passwords are hashed with SHA-256 and a fixed salt.",
            citations=[
                Citation(path="app/auth.py", start_line=6, end_line=7, symbol="hash_password")
            ],
        ),
        Finding(
            claim="Login compares stored hashes.",
            citations=[
                Citation(path="app/auth.py", start_line=14, end_line=15),
                Citation(path="app/auth.py", start_line=6, end_line=7),
            ],
        ),
    ]
)


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> ScriptedChatModel:
    model = ScriptedChatModel(script=[])
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("GOOGLE_API_KEY", "g-test")
    monkeypatch.setattr(cli, "GitHubSource", fixture_source)
    monkeypatch.setattr(cli, "OpenAIEmbedder", fake_embedder)
    monkeypatch.setattr(cli, "CrossEncoderReranker", KeywordReranker)

    def fake_prices() -> PriceTable:
        return FAKE_PRICES

    monkeypatch.setattr(cli, "load_prices", fake_prices)

    def scripted_model(settings: Settings) -> ScriptedChatModel:
        return model

    monkeypatch.setattr(cli, "chat_model", scripted_model)
    return model


def test_ask_prints_a_report_with_citations_cost_and_the_snapshot(
    store: ChunkStore, ledger: Ledger, fakes: ScriptedChatModel
) -> None:
    fakes.script = [FINDINGS, ReportDraft(answer="Passwords are salted SHA-256 hashes [1][2].")]

    result = runner.invoke(cli.app, ["ask", "acme/shop@main", "How are passwords stored?"])

    assert result.exit_code == 0, result.output
    assert result.stdout == (
        f"Snapshot: acme/shop@{SHA}\n"
        "Question: How are passwords stored?\n"
        "\n"
        "Passwords are salted SHA-256 hashes [1][2].\n"
        "\n"
        "[1] Passwords are hashed with SHA-256 and a fixed salt.\n"
        "    app/auth.py:6-7\n"
        "[2] Login compares stored hashes.\n"
        "    app/auth.py:14-15\n"
        "    app/auth.py:6-7\n"
        "\n"
        "Cost: $0.0024 for 2 model calls, at shadow prices\n"
    )
    assert ledger.total_usd() == pytest.approx(2 * CALL_COST)
    assert "Ingested" in result.stderr


def test_ask_reuses_an_ingested_snapshot(
    store: ChunkStore, ledger: Ledger, fakes: ScriptedChatModel
) -> None:
    fakes.script = [CodeFindings(findings=[]), CodeFindings(findings=[])]
    runner.invoke(cli.app, ["ask", "acme/shop", "Where is billing?"])

    result = runner.invoke(cli.app, ["ask", "acme/shop", "Where is billing?"])

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert f"Nothing in acme/shop@{SHA} answers this question." in result.stdout


def test_ask_needs_a_chat_model_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    result = runner.invoke(cli.app, ["ask", "acme/shop", "Where is billing?"])

    assert result.exit_code == 1
    assert "GOOGLE_API_KEY" in result.output


def test_ask_needs_an_openai_key() -> None:
    result = runner.invoke(cli.app, ["ask", "acme/shop", "Where is billing?"])

    assert result.exit_code == 1
    assert "OPENAI_API_KEY" in result.output
