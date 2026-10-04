"""A Report as the web page shows it: each Citation with its code and a link to it on GitHub.

Example answers are saved in this form, so the page shows them without a model call or the
database.
"""

from pathlib import Path
from urllib.parse import quote

from pydantic import BaseModel, TypeAdapter

from repolens.guardrails import redact_secrets
from repolens.report import Report
from repolens.store import ChunkStore

# Display names of the models the demo uses; any other shows its model id.
MODEL_NAMES = {
    "claude-sonnet-5": "Claude Sonnet 5",
    "gemini-3.1-flash-lite": "Gemini 3.1 Flash-Lite",
}


class CitedCode(BaseModel):
    path: str
    start_line: int
    end_line: int
    symbol: str | None
    url: str
    """The lines on GitHub, at the Snapshot's commit."""
    code: str


class CitedFinding(BaseModel):
    claim: str
    citations: list[CitedCode]


class Answer(BaseModel):
    snapshot: str
    question: str
    answer: str
    findings: list[CitedFinding]
    model: str
    """The display name of the model that wrote the answer."""
    rejected: int
    quarantined: list[str] = []
    """The Quarantined chunks the model wasn't shown."""
    calls: int
    input_tokens: int
    output_tokens: int
    duration_s: float


_ANSWERS = TypeAdapter(list[Answer])


def answer_from_report(report: Report, model: str, store: ChunkStore) -> Answer:
    """The Report with the code of each Citation, written by `model` (`provider:model`)."""
    snapshot = report.snapshot
    files: dict[str, dict[int, str]] = {}
    findings: list[CitedFinding] = []
    for finding in report.findings:
        cited: list[CitedCode] = []
        for citation in finding.citations:
            if citation.path not in files:
                files[citation.path] = _lines(store, report, citation.path)
            lines = files[citation.path]
            code = "\n".join(
                lines.get(number, "")
                for number in range(citation.start_line, citation.end_line + 1)
            )
            url = (
                f"https://github.com/{snapshot.owner}/{snapshot.name}/blob/{snapshot.sha}"
                f"/{quote(citation.path)}#L{citation.start_line}-L{citation.end_line}"
            )
            cited.append(CitedCode(**citation.model_dump(), url=url, code=code))
        findings.append(CitedFinding(claim=finding.claim, citations=cited))
    model_id = model.partition(":")[2] or model
    return Answer(
        snapshot=str(snapshot),
        question=report.question,
        answer=report.answer,
        findings=findings,
        model=MODEL_NAMES.get(model_id, model_id),
        rejected=len(report.rejected),
        quarantined=report.quarantined,
        calls=len(report.calls),
        input_tokens=sum(call.input_tokens for call in report.calls),
        output_tokens=sum(call.output_tokens for call in report.calls),
        duration_s=round(report.duration_s, 1),
    )


def load_answers(path: Path) -> list[Answer]:
    return _ANSWERS.validate_json(path.read_bytes()) if path.exists() else []


def save_answer(path: Path, answer: Answer) -> None:
    """Add an example answer to the file, replacing one to the same question."""
    answers = [
        saved
        for saved in load_answers(path)
        if (saved.snapshot, saved.question) != (answer.snapshot, answer.question)
    ]
    answers.append(answer)
    path.write_bytes(_ANSWERS.dump_json(answers, indent=2) + b"\n")


def _lines(store: ChunkStore, report: Report, path: str) -> dict[int, str]:
    """A file's lines by number, from its Chunks, numbered like the Tools number them.

    Secrets are redacted in each whole Chunk, as the Tools redact them.
    """
    lines: dict[int, str] = {}
    for chunk in store.chunks(report.snapshot, [path]):
        for number, line in enumerate(redact_secrets(chunk.text).split("\n"), chunk.start_line):
            lines[number] = line
    return lines
