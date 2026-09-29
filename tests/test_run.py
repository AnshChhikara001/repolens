import json
import re
from pathlib import Path
from typing import Any

import pytest
from fakes import SHA, FakeEmbedder, FixtureSource, KeywordReranker, ScriptedLLM

from repolens.code_navigator import CodeFindings
from repolens.ingest import ingest
from repolens.report import Citation, Finding
from repolens.report_writer import ReportDraft
from repolens.run import RunConfig, run
from repolens.snapshot import RepoRef, Snapshot
from repolens.store import ChunkStore

SNAPSHOT = Snapshot("acme", "shop", SHA)
QUESTION = "How are passwords stored?"

HASHING = Citation(path="app/auth.py", start_line=6, end_line=7, symbol="hash_password")
LOGIN = Citation(path="app/auth.py", start_line=14, end_line=15, symbol="LoginService.login")
HASHED = Finding(claim="Passwords are hashed with SHA-256 and a fixed salt.", citations=[HASHING])
CHECKED = Finding(
    claim="Login compares the stored hash with the hash of the given password.",
    citations=[LOGIN, HASHING],
)


@pytest.fixture
def ingested(store: ChunkStore) -> ChunkStore:
    ingest(RepoRef("acme", "shop"), FixtureSource(), FakeEmbedder(), store)
    return store


@pytest.fixture
def runs_dir(tmp_path: Path) -> Path:
    return tmp_path / "runs"


def config(
    store: ChunkStore,
    llm: ScriptedLLM,
    runs_dir: Path,
    reranker: KeywordReranker | None = None,
) -> RunConfig:
    return RunConfig(
        llm=llm,
        embedder=FakeEmbedder(),
        store=store,
        reranker=reranker or KeywordReranker(),
        runs_dir=runs_dir,
    )


def read_log(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_report_answers_from_cited_findings(ingested: ChunkStore, runs_dir: Path) -> None:
    llm = ScriptedLLM(
        CodeFindings(findings=[HASHED, CHECKED]),
        ReportDraft(answer="Passwords are stored as salted SHA-256 hashes [1][2]."),
    )

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    assert report.question == QUESTION
    assert report.snapshot == SNAPSHOT
    assert report.answer == "Passwords are stored as salted SHA-256 hashes [1][2]."
    assert report.findings == [HASHED, CHECKED]


def test_code_navigator_reads_the_best_reranked_code_first(
    ingested: ChunkStore, runs_dir: Path
) -> None:
    llm = ScriptedLLM(CodeFindings(findings=[HASHED]), ReportDraft(answer="[1]"))

    # Search ranks the password code first for this question; the reranker prefers the API.
    run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir, KeywordReranker("fetch(")))

    prompt = "\n".join(user for _, user in llm.prompts)
    hashing = prompt.index("return hashlib.sha256((SALT + password).encode()).hexdigest()")
    assert prompt.index("fetch(") < hashing


def test_findings_without_citations_are_dropped(ingested: ChunkStore, runs_dir: Path) -> None:
    uncited = Finding(claim="Passwords are stored in plain text.", citations=[])
    llm = ScriptedLLM(CodeFindings(findings=[uncited, HASHED]), ReportDraft(answer="Hashed [1]."))

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    assert report.findings == [HASHED]


@pytest.mark.parametrize(
    "citation",
    [
        Citation(path="app/billing.py", start_line=1, end_line=2),
        Citation(path="app/auth.py", start_line=14, end_line=40),
        Citation(path="app/auth.py", start_line=0, end_line=3),
        Citation(path="app/auth.py", start_line=7, end_line=6),
        Citation(path="app/auth.py", start_line=6, end_line=7, symbol="LoginService.logout"),
        Citation(path="app/auth.py", start_line=6, end_line=7, symbol="LoginService"),
        Citation(path="app/auth.py", start_line=14, end_line=15, symbol="log"),
        Citation(path="app/auth.py", start_line=6, end_line=7, symbol="password"),
    ],
    ids=lambda citation: f"{citation} {citation.symbol or ''}".strip(),
)
def test_a_made_up_citation_is_dropped(
    ingested: ChunkStore, runs_dir: Path, citation: Citation
) -> None:
    made_up = Finding(claim="Passwords are checked against a billing record.", citations=[citation])
    llm = ScriptedLLM(CodeFindings(findings=[made_up, CHECKED]), ReportDraft(answer="Checked [1]."))

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    assert report.findings == [CHECKED]


def test_only_the_valid_citations_of_a_finding_are_kept(
    ingested: ChunkStore, runs_dir: Path
) -> None:
    made_up = Citation(path="app/auth.py", start_line=90, end_line=95)
    partly = Finding(claim=CHECKED.claim, citations=[LOGIN, made_up])
    llm = ScriptedLLM(CodeFindings(findings=[partly]), ReportDraft(answer="Checked [1]."))

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    assert report.findings == [Finding(claim=CHECKED.claim, citations=[LOGIN])]


@pytest.mark.parametrize("symbol", [None, "LoginService", "login", "LoginService.login"])
def test_a_citation_may_name_the_class_or_method_it_points_into(
    ingested: ChunkStore, runs_dir: Path, symbol: str | None
) -> None:
    citation = Citation(path="app/auth.py", start_line=14, end_line=15, symbol=symbol)
    finding = Finding(claim=CHECKED.claim, citations=[citation])
    llm = ScriptedLLM(CodeFindings(findings=[finding]), ReportDraft(answer="Checked [1]."))

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    assert report.findings == [finding]


def test_no_findings_means_a_not_found_report(ingested: ChunkStore, runs_dir: Path) -> None:
    llm = ScriptedLLM(CodeFindings(findings=[]))

    report = run("How is billing done?", SNAPSHOT, config(ingested, llm, runs_dir))

    assert report.findings == []
    assert report.answer == f"Nothing in {SNAPSHOT} answers this question."


def test_findings_with_only_made_up_citations_mean_a_not_found_report(
    ingested: ChunkStore, runs_dir: Path
) -> None:
    made_up = Finding(
        claim="Billing uses Stripe.",
        citations=[Citation(path="app/billing.py", start_line=1, end_line=9)],
    )
    llm = ScriptedLLM(CodeFindings(findings=[made_up]))

    report = run("How is billing done?", SNAPSHOT, config(ingested, llm, runs_dir))

    assert report.findings == []
    assert report.answer == f"Nothing in {SNAPSHOT} answers this question."


def test_a_snapshot_without_chunks_is_answered_without_a_model(
    store: ChunkStore, runs_dir: Path
) -> None:
    report = run(QUESTION, SNAPSHOT, config(store, ScriptedLLM(), runs_dir))

    assert report.findings == []
    assert report.calls == []
    assert "Nothing in" in report.answer
    assert re.search(r"\n\nNo model calls · \d+\.\ds$", str(report))


def test_the_report_ends_with_the_run_usage(ingested: ChunkStore, runs_dir: Path) -> None:
    llm = ScriptedLLM(CodeFindings(findings=[HASHED]), ReportDraft(answer="[1]"))

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    assert [(c.model, c.input_tokens, c.output_tokens) for c in report.calls] == [
        ("fake:scripted", 1000, 100)
    ] * 2
    assert re.search(r"\n\n2 calls · 2,000 in / 200 out tokens · \d+\.\ds$", str(report))


def test_each_run_writes_a_log_of_its_model_calls(ingested: ChunkStore, runs_dir: Path) -> None:
    llm = ScriptedLLM(CodeFindings(findings=[HASHED]), ReportDraft(answer="Hashed [1]."))

    report = run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    events = read_log(runs_dir / f"{report.run_id}.jsonl")
    assert [event.pop("event") for event in events] == ["start", "call", "call", "end"]
    assert all(isinstance(event.pop("time"), str) for event in events)
    start, navigator, writer, end = events
    assert start == {
        "run_id": str(report.run_id),
        "snapshot": str(SNAPSHOT),
        "question": QUESTION,
        "model": "fake:scripted",
    }
    assert navigator == {
        "model": "fake:scripted",
        "schema": "CodeFindings",
        "input_tokens": 1000,
        "output_tokens": 100,
        "latency_s": 0.5,
    }
    assert writer["schema"] == "ReportDraft"
    assert end["findings"] == 1
    assert end["answer"] == "Hashed [1]."
    assert end["duration_s"] == report.duration_s


def test_a_failed_run_logs_its_calls_and_the_error(ingested: ChunkStore, runs_dir: Path) -> None:
    llm = ScriptedLLM(CodeFindings(findings=[HASHED]))  # no answer to write

    with pytest.raises(AssertionError, match="no scripted answer"):
        run(QUESTION, SNAPSHOT, config(ingested, llm, runs_dir))

    [log] = runs_dir.glob("*.jsonl")
    events = read_log(log)
    assert [event["event"] for event in events] == ["start", "call", "error"]
    assert "no scripted answer for ReportDraft" in events[2]["error"]
