import re
from pathlib import Path

import pytest
from fakes import NOTHING_NEW, SHA, FailingLLM, ScriptedLLM
from typer.testing import CliRunner

from repolens import cli
from repolens.code_navigator import AgentAction
from repolens.config import Settings
from repolens.llm import LLMError
from repolens.report import Citation, Finding
from repolens.report_writer import ReportDraft
from repolens.store import ChunkStore

runner = CliRunner()
pytestmark = pytest.mark.usefixtures("clean_env")

FINDINGS = AgentAction(
    action="answer",
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
    ],
)


USAGE = r"3 calls · 3,000 in / 300 out tokens · \d+\.\ds\n"


def test_ask_prints_a_report_with_citations_usage_and_the_snapshot(
    store: ChunkStore, fakes: ScriptedLLM
) -> None:
    fakes.script.extend(
        [NOTHING_NEW, FINDINGS, ReportDraft(answer="Passwords are salted SHA-256 hashes [1][2].")]
    )

    result = runner.invoke(cli.app, ["ask", "acme/shop@main", "How are passwords stored?"])

    assert result.exit_code == 0, result.output
    report, usage = result.stdout.rsplit("\n\n", 1)
    assert report == (
        f"Snapshot: acme/shop@{SHA}\n"
        "Question: How are passwords stored?\n"
        "\n"
        "Passwords are salted SHA-256 hashes [1][2].\n"
        "\n"
        "[1] Passwords are hashed with SHA-256 and a fixed salt.\n"
        "    app/auth.py:6-7\n"
        "[2] Login compares stored hashes.\n"
        "    app/auth.py:14-15\n"
        "    app/auth.py:6-7"
    )
    assert re.fullmatch(USAGE, usage)
    assert "Ingested" in result.stderr


def test_ask_writes_a_run_log(store: ChunkStore, fakes: ScriptedLLM, tmp_path: Path) -> None:
    fakes.script.extend([NOTHING_NEW, AgentAction(action="answer")])

    result = runner.invoke(cli.app, ["ask", "acme/shop", "Where is billing?"])

    assert result.exit_code == 0, result.output
    assert len(list((tmp_path / "runs").glob("*.jsonl"))) == 1


def test_ask_reuses_an_ingested_snapshot(store: ChunkStore, fakes: ScriptedLLM) -> None:
    fakes.script.extend([NOTHING_NEW, AgentAction(action="answer")] * 2)
    runner.invoke(cli.app, ["ask", "acme/shop", "Where is billing?"])

    result = runner.invoke(cli.app, ["ask", "acme/shop", "Where is billing?"])

    assert result.exit_code == 0, result.output
    assert result.stderr == "Answering with google:gemini-3.1-flash-lite…\n"
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


# A local models file whose model finds nothing, in two calls.
LOCAL_MODELS = """
from fakes import NOTHING_NEW, ScriptedLLM
from repolens.code_navigator import AgentAction


def llm(name, timeout):
    return ScriptedLLM(NOTHING_NEW, AgentAction(action="answer"))
"""


def test_ask_runs_a_model_from_the_local_models_file(
    store: ChunkStore,
    offline: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_models = tmp_path / "models.py"
    local_models.write_text(LOCAL_MODELS)
    monkeypatch.setenv("LOCAL_MODELS", str(local_models))
    monkeypatch.setenv("CHAT_MODEL", "fake:scripted")

    result = runner.invoke(cli.app, ["ask", "acme/shop", "Where is billing?"])

    assert result.exit_code == 0, result.output
    assert re.search(r"\n\n2 calls · 2,000 in / 200 out tokens · \d+\.\ds\n$", result.stdout)
    assert "Answering with fake:scripted…" in result.stderr


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            TimeoutError(),
            "error: a chat model request took longer than 30s, raise CHAT_TIMEOUT to wait longer\n",
        ),
        (
            LLMError("google:gemini-x: 503 UNAVAILABLE, The model is overloaded."),
            "error: google:gemini-x: 503 UNAVAILABLE, The model is overloaded.\n",
        ),
    ],
    ids=["timeout", "provider error"],
)
def test_a_failing_model_fails_the_run_with_one_clear_line(
    store: ChunkStore,
    fakes: ScriptedLLM,
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
    message: str,
) -> None:
    monkeypatch.setenv("CHAT_TIMEOUT", "30")

    def failing_model(settings: Settings) -> FailingLLM:
        return FailingLLM(error)

    monkeypatch.setattr(cli, "build_llm", failing_model)

    result = runner.invoke(cli.app, ["ask", "acme/shop", "Where is billing?"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.endswith(message)
    assert result.stderr.count("error:") == 1
