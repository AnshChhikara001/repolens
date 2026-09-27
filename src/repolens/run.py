"""A Run: one question answered against one Snapshot.

For now the graph is a single fixed Step: the Code Navigator finds cited Findings and the
Report Writer turns them into a Report. The Supervisor replaces the fixed Step in M2.
"""

from dataclasses import dataclass
from typing import NotRequired, TypedDict

from langchain_core.language_models import BaseChatModel
from langgraph.graph import START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from repolens.code_navigator import find_code
from repolens.embedding import Embedder
from repolens.report import Finding, Report
from repolens.report_writer import write_answer
from repolens.snapshot import Snapshot
from repolens.store import ChunkStore

NOT_FOUND = "No code in this Snapshot answers the question."


@dataclass(frozen=True)
class RunConfig:
    model: BaseChatModel
    embedder: Embedder
    store: ChunkStore


class RunState(TypedDict):
    question: str
    snapshot: Snapshot
    findings: NotRequired[list[Finding]]
    answer: NotRequired[str]


class RunUpdate(TypedDict, total=False):
    findings: list[Finding]
    answer: str


def run(question: str, snapshot: Snapshot, config: RunConfig) -> Report:
    """Answer a question about an ingested Snapshot with a Report of cited Findings."""
    graph = _graph(config)
    output = graph.invoke(  # pyright: ignore[reportUnknownMemberType]
        {"question": question, "snapshot": snapshot}, version="v2"
    )
    state = output.value
    return Report(question, snapshot, state.get("answer", NOT_FOUND), state.get("findings", []))


def _graph(config: RunConfig) -> CompiledStateGraph[RunState, None, RunState, RunState]:
    def code_navigator(state: RunState) -> RunUpdate:
        findings = find_code(
            state["question"], state["snapshot"], config.model, config.embedder, config.store
        )
        return {"findings": findings}

    def report_writer(state: RunState) -> RunUpdate:
        findings = state.get("findings", [])
        if not findings:
            return {"answer": NOT_FOUND}
        return {"answer": write_answer(state["question"], findings, config.model)}

    # LangGraph's signatures mention unparametrised generics, hence the ignores.
    graph = StateGraph(RunState)
    graph.add_sequence([code_navigator, report_writer])  # pyright: ignore[reportUnknownMemberType]
    graph.add_edge(START, "code_navigator")
    return graph.compile()  # pyright: ignore[reportUnknownMemberType]
