import pytest
from fakes import (
    CALL_COST,
    FAKE_PRICES,
    SHA,
    FakeEmbedder,
    FixtureSource,
    KeywordReranker,
    ScriptedChatModel,
)

from repolens.code_navigator import CodeFindings
from repolens.config import ModelConfigError
from repolens.costs import Price, PriceTable
from repolens.ingest import ingest
from repolens.ledger import Ledger
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


def config(
    store: ChunkStore,
    ledger: Ledger,
    model: ScriptedChatModel,
    reranker: KeywordReranker | None = None,
    prices: PriceTable = FAKE_PRICES,
) -> RunConfig:
    return RunConfig(
        model=model,
        embedder=FakeEmbedder(),
        store=store,
        reranker=reranker or KeywordReranker(),
        prices=prices,
        ledger=ledger,
    )


def test_report_answers_from_cited_findings(ingested: ChunkStore, ledger: Ledger) -> None:
    model = ScriptedChatModel(
        script=[
            CodeFindings(findings=[HASHED, CHECKED]),
            ReportDraft(answer="Passwords are stored as salted SHA-256 hashes [1][2]."),
        ]
    )

    report = run(QUESTION, SNAPSHOT, config(ingested, ledger, model))

    assert report.question == QUESTION
    assert report.snapshot == SNAPSHOT
    assert report.answer == "Passwords are stored as salted SHA-256 hashes [1][2]."
    assert report.findings == [HASHED, CHECKED]


def test_code_navigator_reads_the_best_reranked_code_first(
    ingested: ChunkStore, ledger: Ledger
) -> None:
    model = ScriptedChatModel(script=[CodeFindings(findings=[HASHED]), ReportDraft(answer="[1]")])

    # Search ranks the password code first for this question; the reranker prefers the API.
    run(QUESTION, SNAPSHOT, config(ingested, ledger, model, KeywordReranker("fetch(")))

    prompt = "\n".join(str(message.content) for prompt in model.prompts for message in prompt)
    hashing = prompt.index("return hashlib.sha256((SALT + password).encode()).hexdigest()")
    assert prompt.index("fetch(") < hashing


def test_findings_without_citations_are_dropped(ingested: ChunkStore, ledger: Ledger) -> None:
    uncited = Finding(claim="Passwords are stored in plain text.", citations=[])
    model = ScriptedChatModel(
        script=[CodeFindings(findings=[uncited, HASHED]), ReportDraft(answer="Hashed [1].")]
    )

    report = run(QUESTION, SNAPSHOT, config(ingested, ledger, model))

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
    ingested: ChunkStore, ledger: Ledger, citation: Citation
) -> None:
    made_up = Finding(claim="Passwords are checked against a billing record.", citations=[citation])
    model = ScriptedChatModel(
        script=[CodeFindings(findings=[made_up, CHECKED]), ReportDraft(answer="Checked [1].")]
    )

    report = run(QUESTION, SNAPSHOT, config(ingested, ledger, model))

    assert report.findings == [CHECKED]


def test_only_the_valid_citations_of_a_finding_are_kept(
    ingested: ChunkStore, ledger: Ledger
) -> None:
    made_up = Citation(path="app/auth.py", start_line=90, end_line=95)
    partly = Finding(claim=CHECKED.claim, citations=[LOGIN, made_up])
    model = ScriptedChatModel(
        script=[CodeFindings(findings=[partly]), ReportDraft(answer="Checked [1].")]
    )

    report = run(QUESTION, SNAPSHOT, config(ingested, ledger, model))

    assert report.findings == [Finding(claim=CHECKED.claim, citations=[LOGIN])]


@pytest.mark.parametrize("symbol", [None, "LoginService", "login", "LoginService.login"])
def test_a_citation_may_name_the_class_or_method_it_points_into(
    ingested: ChunkStore, ledger: Ledger, symbol: str | None
) -> None:
    citation = Citation(path="app/auth.py", start_line=14, end_line=15, symbol=symbol)
    finding = Finding(claim=CHECKED.claim, citations=[citation])
    model = ScriptedChatModel(
        script=[CodeFindings(findings=[finding]), ReportDraft(answer="Checked [1].")]
    )

    report = run(QUESTION, SNAPSHOT, config(ingested, ledger, model))

    assert report.findings == [finding]


def test_no_findings_means_a_not_found_report(ingested: ChunkStore, ledger: Ledger) -> None:
    model = ScriptedChatModel(script=[CodeFindings(findings=[])])

    report = run("How is billing done?", SNAPSHOT, config(ingested, ledger, model))

    assert report.findings == []
    assert report.answer == f"Nothing in {SNAPSHOT} answers this question."


def test_findings_with_only_made_up_citations_mean_a_not_found_report(
    ingested: ChunkStore, ledger: Ledger
) -> None:
    made_up = Finding(
        claim="Billing uses Stripe.",
        citations=[Citation(path="app/billing.py", start_line=1, end_line=9)],
    )
    model = ScriptedChatModel(script=[CodeFindings(findings=[made_up])])

    report = run("How is billing done?", SNAPSHOT, config(ingested, ledger, model))

    assert report.findings == []
    assert report.answer == f"Nothing in {SNAPSHOT} answers this question."


def test_a_snapshot_without_chunks_is_answered_without_a_model(
    store: ChunkStore, ledger: Ledger
) -> None:
    report = run(QUESTION, SNAPSHOT, config(store, ledger, ScriptedChatModel(script=[])))

    assert report.findings == []
    assert report.calls == []
    assert "Nothing in" in report.answer
    assert str(report).endswith("\n\nCost: $0.0000 (no model calls)")


def test_the_report_shows_the_run_cost(ingested: ChunkStore, ledger: Ledger) -> None:
    model = ScriptedChatModel(script=[CodeFindings(findings=[HASHED]), ReportDraft(answer="[1]")])

    report = run(QUESTION, SNAPSHOT, config(ingested, ledger, model))

    assert report.cost_usd == pytest.approx(2 * CALL_COST)
    assert str(report).endswith("\n\nShadow cost: $0.0024 (scripted, 2 calls)")


def test_a_run_on_a_paid_model_shows_its_real_cost(ingested: ChunkStore, ledger: Ledger) -> None:
    model = ScriptedChatModel(script=[CodeFindings(findings=[])])
    paid = PriceTable({"fake:scripted": Price(input=1.0, output=2.0)})

    report = run(QUESTION, SNAPSHOT, config(ingested, ledger, model, prices=paid))

    assert str(report).endswith("\n\nCost: $0.0012 (scripted, 1 call)")


def test_the_ledger_has_one_row_per_model_call(ingested: ChunkStore, ledger: Ledger) -> None:
    model = ScriptedChatModel(script=[CodeFindings(findings=[HASHED]), ReportDraft(answer="[1]")])

    report = run(QUESTION, SNAPSHOT, config(ingested, ledger, model))

    calls = ledger.calls(report.run_id)
    assert calls == report.calls
    assert [(c.model, c.input_tokens, c.output_tokens, c.shadow) for c in calls] == [
        ("fake:scripted", 1000, 100, True)
    ] * 2
    assert [c.cost_usd for c in calls] == [pytest.approx(CALL_COST)] * 2


def test_the_ledger_keeps_the_calls_of_a_failed_run(ingested: ChunkStore, ledger: Ledger) -> None:
    model = ScriptedChatModel(script=[CodeFindings(findings=[HASHED])])  # no answer to write

    with pytest.raises(AssertionError, match="no scripted answer"):
        run(QUESTION, SNAPSHOT, config(ingested, ledger, model))

    assert ledger.total_usd() == pytest.approx(CALL_COST)


def test_an_unpriced_model_is_not_called(ingested: ChunkStore, ledger: Ledger) -> None:
    model = ScriptedChatModel(script=[CodeFindings(findings=[HASHED])])

    with pytest.raises(ModelConfigError, match="fake:scripted"):
        run(QUESTION, SNAPSHOT, config(ingested, ledger, model, prices=PriceTable({})))

    assert model.prompts == []
