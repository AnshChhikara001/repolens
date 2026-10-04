"""A Run: one question answered against one Snapshot.

The Code Navigator searches and reads the code until it can answer with cited Findings, the
citation verifier drops those that cite lines the model wasn't shown (ADR-0007), and the Report
Writer turns the rest into a Report. Secrets are redacted from the Report, as from the code the
model was shown (ADR-0015). Every model call is counted in the Report and written to
the run log, with each Agent step and Tool result, the rejected Citations and why a failed Run
failed.
"""

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from repolens.citations import verify
from repolens.code_navigator import MAX_STEPS, find_code
from repolens.embedding import Embedder
from repolens.guardrails import redact_secrets
from repolens.lines_read import LinesRead
from repolens.llm import LLM, ModelCall, Reply
from repolens.report import Finding, Report
from repolens.report_writer import write_answer
from repolens.rerank import Reranker
from repolens.run_log import OnEvent, RunLog
from repolens.snapshot import Snapshot
from repolens.store import ChunkStore
from repolens.tools import Tools

NOT_FOUND = "Nothing in {snapshot} answers this question."


@dataclass(frozen=True)
class RunConfig:
    """The model, stores and log directory a Run uses, and how many Agent steps it may take.

    No reranker keeps the search order.
    """

    llm: LLM
    embedder: Embedder
    store: ChunkStore
    reranker: Reranker | None
    runs_dir: Path
    max_steps: int = MAX_STEPS


def run(
    question: str, snapshot: Snapshot, config: RunConfig, on_event: OnEvent | None = None
) -> Report:
    """Answer a question about an ingested Snapshot with a Report of verified Findings.

    `on_event` gets each Run log event as it is written, to show the Run's progress live.
    """
    run_id = uuid4()
    started = time.perf_counter()
    log = RunLog(config.runs_dir / f"{run_id}.jsonl", on_event)
    log.write("start", run_id=run_id, snapshot=snapshot, question=question, model=config.llm.name)
    llm = _RecordingLLM(config.llm, log)
    lines_read = LinesRead()
    try:
        tools = Tools(snapshot, config.embedder, config.store, config.reranker, lines_read)
        findings = find_code(question, llm, tools, log, config.max_steps)
        findings, rejected = verify(findings, lines_read)
        findings = [Finding(claim=redact_secrets(f.claim), citations=f.citations) for f in findings]
        if findings:
            answer = redact_secrets(write_answer(question, findings, llm))
        else:
            answer = NOT_FOUND.format(snapshot=snapshot)
    except BaseException as exc:
        log.write("error", error=repr(exc))
        raise
    duration_s = time.perf_counter() - started
    log.write(
        "end",
        findings=len(findings),
        rejected=[f"{c} {c.symbol}" if c.symbol else str(c) for c in rejected],
        quarantined=tools.quarantined,
        answer=answer,
        duration_s=duration_s,
    )
    return Report(
        run_id=run_id,
        question=question,
        snapshot=snapshot,
        answer=answer,
        findings=findings,
        rejected=rejected,
        quarantined=tools.quarantined,
        calls=llm.calls,
        duration_s=duration_s,
    )


class _RecordingLLM:
    """Passes calls on to the Run's model and records each one."""

    def __init__(self, llm: LLM, log: RunLog) -> None:
        self.name = llm.name
        self.calls: list[ModelCall] = []
        self._llm = llm
        self._log = log

    def structured[T: BaseModel](self, system: str, user: str, schema: type[T]) -> Reply[T]:
        reply = self._llm.structured(system, user, schema)
        call = ModelCall(
            self.name, schema.__name__, reply.input_tokens, reply.output_tokens, reply.latency_s
        )
        self.calls.append(call)
        self._log.write("call", **asdict(call))
        return reply
