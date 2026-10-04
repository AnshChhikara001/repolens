from pathlib import Path
from uuid import uuid4

import pytest

from repolens.evaluation import Outcome, Question, evaluate, load_questions, results_table
from repolens.llm import LLMError, ModelCall
from repolens.report import Citation, Finding, Report
from repolens.snapshot import Snapshot

SHA = "a" * 40
SNAPSHOT = Snapshot("acme", "shop", SHA)

PASSWORDS = Question(
    id="passwords",
    repo=f"acme/shop@{SHA}",
    question="How are passwords stored?",
    expected_files=["app/auth.py", "app/config.py"],
    expected_symbols=["hash_password", "LoginService.login"],
)
BILLING = Question(
    id="billing",
    repo=f"acme/shop@{SHA}",
    question="How is billing done?",
    expected_files=["app/billing.py"],
)

HASHING = Citation(path="app/auth.py", start_line=6, end_line=7, symbol="hash_password")
LOGIN = Citation(path="app/auth.py", start_line=14, end_line=15, symbol="auth.LoginService.login")
API = Citation(path="web/src/api.ts", start_line=5, end_line=8)


def call(model: str = "google:gemini-3.1-flash-lite", latency_s: float = 2.0) -> ModelCall:
    return ModelCall(model, "CodeFindings", 10_000, 1_000, latency_s)


def report(
    findings: list[Finding],
    rejected: list[Citation] | None = None,
    calls: list[ModelCall] | None = None,
    duration_s: float = 5.0,
) -> Report:
    return Report(
        run_id=uuid4(),
        question="?",
        snapshot=SNAPSHOT,
        answer="An answer [1].",
        findings=findings,
        rejected=rejected or [],
        quarantined=[],
        calls=[call(), call()] if calls is None else calls,
        duration_s=duration_s,
    )


def rows(table: str) -> dict[str, list[str]]:
    """The cells of each markdown table row, keyed by its first cell."""
    cells = [
        [cell.strip() for cell in line.strip("|").split("|")]
        for line in table.splitlines()
        if line.startswith("|")
    ]
    return {row[0]: row[1:] for row in cells}


def test_questions_are_read_from_a_toml_file(tmp_path: Path) -> None:
    path = tmp_path / "questions.toml"
    path.write_text(
        f"""
[[questions]]
id = "passwords"
repo = "acme/shop@{SHA}"
question = "How are passwords stored?"
expected_files = ["app/auth.py", "app/config.py"]
expected_symbols = ["hash_password", "LoginService.login"]

[[questions]]
id = "billing"
repo = "acme/shop@{SHA}"
question = "How is billing done?"
expected_files = ["app/billing.py"]
"""
    )

    assert load_questions(path) == [PASSWORDS, BILLING]


@pytest.mark.parametrize(
    ("repo", "problem"),
    [("acme/shop", "pinned"), ("acme/shop@main", "pinned"), ("acme/shop@abc123", "pinned")],
)
def test_every_question_is_pinned_to_a_full_commit_sha(
    tmp_path: Path, repo: str, problem: str
) -> None:
    path = tmp_path / "questions.toml"
    path.write_text(
        f'[[questions]]\nid = "q"\nrepo = "{repo}"\nquestion = "?"\nexpected_files = ["a.py"]\n'
    )

    with pytest.raises(ValueError, match=problem):
        load_questions(path)


def test_question_ids_are_unique(tmp_path: Path) -> None:
    question = f'[[questions]]\nid = "q"\nrepo = "acme/shop@{SHA}"\nquestion = "?"\n'
    path = tmp_path / "questions.toml"
    path.write_text(f'{question}expected_files = ["a.py"]\n{question}expected_files = ["b.py"]\n')

    with pytest.raises(ValueError, match="duplicate question id 'q'"):
        load_questions(path)


def test_evaluate_answers_every_question_and_records_model_errors() -> None:
    answered = report([Finding(claim="Hashed.", citations=[HASHING])])

    def answer(question: Question) -> Report:
        if question is BILLING:
            raise LLMError("google:gemini-3.1-flash-lite: 503 UNAVAILABLE")
        return answered

    outcomes = evaluate([PASSWORDS, BILLING], answer)

    assert outcomes == [
        Outcome(PASSWORDS, answered),
        Outcome(BILLING, error="google:gemini-3.1-flash-lite: 503 UNAVAILABLE"),
    ]


def test_evaluate_records_timeouts() -> None:
    def answer(question: Question) -> Report:
        raise TimeoutError("google:gemini-3.1-flash-lite timed out")

    [outcome] = evaluate([BILLING], answer)

    assert outcome.error == "google:gemini-3.1-flash-lite timed out"


def test_results_score_each_question_by_its_verified_citations() -> None:
    findings = [
        Finding(claim="Hashed.", citations=[HASHING]),
        Finding(claim="Checked.", citations=[LOGIN, API]),
    ]
    made_up = Citation(path="app/config.py", start_line=90, end_line=95)
    outcomes = [
        Outcome(PASSWORDS, report(findings, rejected=[made_up], duration_s=6.0)),
        Outcome(BILLING, report([], calls=[call()], duration_s=3.0)),
    ]

    table = rows(results_table(outcomes))

    # Question: files, symbols, citations valid, findings, model s, run s, tokens, est. cost
    assert table["passwords"] == [
        "1/2",
        "2/2",
        "3/4",
        "2",
        "4.0",
        "6.0",
        "20,000 / 2,000",
        "$0.0080",
    ]
    assert table["billing"] == ["0/1", "-", "0/0", "0", "2.0", "3.0", "10,000 / 1,000", "$0.0040"]


def test_results_summarise_the_whole_eval() -> None:
    outcomes = [
        Outcome(PASSWORDS, report([Finding(claim="Hashed.", citations=[HASHING])])),
        Outcome(BILLING, report([], rejected=[API], calls=[call()], duration_s=3.0)),
        Outcome(BILLING, error="503"),
    ]

    table = rows(results_table(outcomes))

    assert table["Questions"] == ["3 (1 error)"]
    assert table["Citation validity"] == ["1/2 (50%)"]
    assert table["Expected-file recall"] == ["25%"]  # (1/2 + 0/1) / 2
    assert table["Expected-symbol recall"] == ["50% (1 question)"]
    assert table["Found nothing"] == ["1/2 (50%)"]
    assert table["Model latency"] == ["3.0s mean"]
    assert table["Run time"] == ["4.0s mean"]
    assert table["Tokens"] == ["15,000 in / 1,500 out mean"]
    assert table["Est. cost"] == ["$0.0060 mean, $0.0120 total"]


def test_errors_are_listed_under_the_results() -> None:
    table = results_table([Outcome(BILLING, error="google:gemini-3.1-flash-lite timed out")])

    assert rows(table)["billing"][0] == "error"
    assert "- billing: google:gemini-3.1-flash-lite timed out" in table


def test_cost_is_estimated_at_list_prices_by_model_name() -> None:
    calls = [call("anthropic:claude-sonnet-5"), call("other:claude-sonnet-5")]
    outcomes = [Outcome(BILLING, report([], calls=calls))]

    # $2 in / $10 out per 1M tokens: 2 x (10,000 x 2 + 1,000 x 10) / 1M
    assert rows(results_table(outcomes))["billing"][-1] == "$0.0600"


def test_a_model_without_a_list_price_has_no_cost_estimate() -> None:
    outcomes = [Outcome(BILLING, report([], calls=[call("local:mystery-7b")]))]

    table = rows(results_table(outcomes))

    assert table["billing"][-1] == "-"
    assert table["Est. cost"] == ["-"]


def test_an_expected_symbol_counts_only_in_an_expected_file() -> None:
    elsewhere = Citation(path="app/legacy.py", start_line=1, end_line=5, symbol="hash_password")
    outcomes = [Outcome(PASSWORDS, report([Finding(claim="Hashed.", citations=[elsewhere])]))]

    assert rows(results_table(outcomes))["passwords"][1] == "0/2"
