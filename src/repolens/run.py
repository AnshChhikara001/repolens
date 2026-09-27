"""A Run: one question answered against one Snapshot.

For now the graph is a single fixed Step: the Code Navigator finds cited Findings, the
citation verifier drops those the Snapshot doesn't back (ADR-0007), and the Report Writer
turns the rest into a Report. The Supervisor replaces the fixed Step in M2. Every model call
is priced and written to the cost ledger, even when the Run fails (ADR-0004).
"""

from contextlib import suppress
from dataclasses import dataclass
from typing import NotRequired, TypedDict
from uuid import uuid4

import psycopg
from langchain_core.language_models import BaseChatModel
from langgraph.graph import START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from repolens.citations import verify
from repolens.code_navigator import find_code
from repolens.costs import CostTracker, PriceTable
from repolens.embedding import Embedder
from repolens.ledger import Ledger
from repolens.report import Finding, Report
from repolens.report_writer import write_answer
from repolens.rerank import Reranker
from repolens.snapshot import Snapshot
from repolens.store import ChunkStore

NOT_FOUND = "Nothing in {snapshot} answers this question."


@dataclass(frozen=True)
class RunConfig:
    """The models and stores a Run uses."""

    model: BaseChatModel
    embedder: Embedder
    store: ChunkStore
    reranker: Reranker
    prices: PriceTable
    ledger: Ledger


class RunState(TypedDict):
    question: str
    snapshot: Snapshot
    findings: NotRequired[list[Finding]]
    answer: NotRequired[str]


class RunUpdate(TypedDict, total=False):
    findings: list[Finding]
    answer: str


def run(question: str, snapshot: Snapshot, config: RunConfig) -> Report:
    """Answer a question about an ingested Snapshot with a Report of verified Findings."""
    run_id = uuid4()
    tracker = CostTracker(config.prices)
    try:
        output = _graph(config).invoke(  # pyright: ignore[reportUnknownMemberType]
            {"question": question, "snapshot": snapshot},
            {"callbacks": [tracker], "run_id": run_id},
            version="v2",
        )
    except BaseException:
        # Record what the failed Run spent, without hiding why it failed.
        with suppress(psycopg.Error):
            config.ledger.record(run_id, snapshot, tracker.calls)
        raise
    config.ledger.record(run_id, snapshot, tracker.calls)
    state = output.value
    return Report(
        run_id=run_id,
        question=question,
        snapshot=snapshot,
        answer=state.get("answer", NOT_FOUND.format(snapshot=snapshot)),
        findings=state.get("findings", []),
        calls=tracker.calls,
    )


def _graph(config: RunConfig) -> CompiledStateGraph[RunState, None, RunState, RunState]:
    def code_navigator(state: RunState) -> RunUpdate:
        findings = find_code(
            state["question"],
            state["snapshot"],
            config.model,
            config.embedder,
            config.store,
            config.reranker,
        )
        return {"findings": findings}

    def citation_verifier(state: RunState) -> RunUpdate:
        return {"findings": verify(state.get("findings", []), state["snapshot"], config.store)}

    def report_writer(state: RunState) -> RunUpdate:
        findings = state.get("findings", [])
        if not findings:
            return {"answer": NOT_FOUND.format(snapshot=state["snapshot"])}
        return {"answer": write_answer(state["question"], findings, config.model)}

    # LangGraph's signatures mention unparametrised generics, hence the ignores.
    graph = StateGraph(RunState)
    graph.add_sequence([code_navigator, citation_verifier, report_writer])  # pyright: ignore[reportUnknownMemberType]
    graph.add_edge(START, "code_navigator")
    return graph.compile()  # pyright: ignore[reportUnknownMemberType]
