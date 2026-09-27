import pytest
from fakes import SHA, FakeEmbedder, FixtureSource, ScriptedChatModel

from repolens.code_navigator import CodeFindings
from repolens.ingest import ingest
from repolens.report import Citation, Finding, Report
from repolens.report_writer import ReportDraft
from repolens.run import RunConfig, run
from repolens.snapshot import RepoRef, Snapshot
from repolens.store import ChunkStore

SNAPSHOT = Snapshot("acme", "shop", SHA)
QUESTION = "How are passwords stored?"

HASHED = Finding(
    claim="Passwords are hashed with SHA-256 and a fixed salt.",
    citations=[Citation(path="app/auth.py", start_line=6, end_line=7)],
)
CHECKED = Finding(
    claim="Login compares the stored hash with the hash of the given password.",
    citations=[
        Citation(path="app/auth.py", start_line=14, end_line=15),
        Citation(path="app/auth.py", start_line=6, end_line=7),
    ],
)


@pytest.fixture
def ingested(store: ChunkStore) -> ChunkStore:
    ingest(RepoRef("acme", "shop"), FixtureSource(), FakeEmbedder(), store)
    return store


def config(store: ChunkStore, model: ScriptedChatModel) -> RunConfig:
    return RunConfig(model=model, embedder=FakeEmbedder(), store=store)


def test_report_answers_from_cited_findings(ingested: ChunkStore) -> None:
    model = ScriptedChatModel(
        script=[
            CodeFindings(findings=[HASHED, CHECKED]),
            ReportDraft(answer="Passwords are stored as salted SHA-256 hashes [1][2]."),
        ]
    )

    report = run(QUESTION, SNAPSHOT, config(ingested, model))

    assert report == Report(
        question=QUESTION,
        snapshot=SNAPSHOT,
        answer="Passwords are stored as salted SHA-256 hashes [1][2].",
        findings=[HASHED, CHECKED],
    )


def test_code_navigator_reads_the_retrieved_code(ingested: ChunkStore) -> None:
    model = ScriptedChatModel(script=[CodeFindings(findings=[HASHED]), ReportDraft(answer="[1]")])

    run(QUESTION, SNAPSHOT, config(ingested, model))

    code = "return hashlib.sha256((SALT + password).encode()).hexdigest()"
    assert any(code in str(message.content) for prompt in model.prompts for message in prompt)


def test_findings_without_citations_are_dropped(ingested: ChunkStore) -> None:
    uncited = Finding(claim="Passwords are stored in plain text.", citations=[])
    model = ScriptedChatModel(
        script=[CodeFindings(findings=[uncited, HASHED]), ReportDraft(answer="Hashed [1].")]
    )

    report = run(QUESTION, SNAPSHOT, config(ingested, model))

    assert report.findings == [HASHED]


def test_no_findings_means_a_not_found_report(ingested: ChunkStore) -> None:
    model = ScriptedChatModel(script=[CodeFindings(findings=[])])

    report = run("How is billing done?", SNAPSHOT, config(ingested, model))

    assert report.findings == []
    assert "No code" in report.answer


def test_a_snapshot_without_chunks_is_answered_without_a_model(store: ChunkStore) -> None:
    report = run(QUESTION, SNAPSHOT, config(store, ScriptedChatModel(script=[])))

    assert report.findings == []
    assert "No code" in report.answer
