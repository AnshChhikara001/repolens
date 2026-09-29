from pathlib import Path

import pytest
from fakes import SHA, ScriptedLLM
from typer.testing import CliRunner

from repolens import cli
from repolens.code_navigator import CodeFindings
from repolens.report import Citation, Finding
from repolens.report_writer import ReportDraft
from repolens.store import ChunkStore

runner = CliRunner()
pytestmark = pytest.mark.usefixtures("clean_env")

QUESTIONS = f"""
[[questions]]
id = "passwords"
repo = "acme/shop@{SHA}"
question = "How are passwords stored?"
expected_files = ["app/auth.py"]
expected_symbols = ["hash_password"]

[[questions]]
id = "billing"
repo = "acme/shop@{SHA}"
question = "How is billing done?"
expected_files = ["app/billing.py"]
"""

HASHED = Finding(
    claim="Passwords are hashed with SHA-256 and a fixed salt.",
    citations=[Citation(path="app/auth.py", start_line=6, end_line=7, symbol="hash_password")],
)


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    path = tmp_path / "questions.toml"
    path.write_text(QUESTIONS)
    return path


def test_eval_prints_the_results_of_every_question(
    store: ChunkStore, fakes: ScriptedLLM, dataset: Path
) -> None:
    fakes.script.extend(
        [CodeFindings(findings=[HASHED]), ReportDraft(answer="[1]"), CodeFindings(findings=[])]
    )

    result = runner.invoke(cli.app, ["eval", "--dataset", str(dataset)])

    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("Model: scripted · Reranking: on\n\n| Metric | Value |")
    assert "| Found nothing | 1/2 (50%) |" in result.stdout
    assert "| passwords | 1/1 | 1/1 | 1/1 | 1 |" in result.stdout
    assert "| billing | 0/1 | - | 0/0 | 0 |" in result.stdout
    assert result.stderr == (
        f"Ingested acme/shop@{SHA}: 6 chunks from 5 files\n[1/2] passwords\n[2/2] billing\n"
    )


def test_eval_can_run_without_reranking(
    store: ChunkStore, fakes: ScriptedLLM, dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_reranker() -> None:
        raise AssertionError("the reranker was loaded")

    monkeypatch.setattr(cli, "CrossEncoderReranker", no_reranker)
    fakes.script.extend([CodeFindings(findings=[]), CodeFindings(findings=[])])

    result = runner.invoke(cli.app, ["eval", "--dataset", str(dataset), "--no-rerank"])

    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("Model: scripted · Reranking: off\n")


@pytest.mark.parametrize(
    ("questions", "message"),
    [
        (QUESTIONS.replace(f"@{SHA}", "@main", 1), "passwords: acme/shop@main is not pinned"),
        ("[[questions]]\nid = 1", "questions.0"),
        (None, "No such file"),
    ],
    ids=["unpinned", "invalid", "missing"],
)
def test_an_invalid_dataset_fails_with_an_error(
    fakes: ScriptedLLM, tmp_path: Path, questions: str | None, message: str
) -> None:
    path = tmp_path / "questions.toml"
    if questions is not None:
        path.write_text(questions)

    result = runner.invoke(cli.app, ["eval", "--dataset", str(path)])

    assert result.exit_code == 1
    assert result.stderr.startswith(f"error: {path}: ")
    assert message in result.stderr
