"""Findings, Citations and the Report a Run returns (ADR-0007)."""

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, Field

from repolens.llm import ModelCall
from repolens.snapshot import Snapshot


class Citation(BaseModel):
    """A line range in a file at the analysed commit."""

    path: str = Field(description="File path relative to the repository root.")
    start_line: int = Field(description="First cited line, 1-based.")
    end_line: int = Field(description="Last cited line, inclusive.")
    symbol: str | None = Field(
        default=None,
        description="The function, class or method the lines are in, e.g. `LoginService.login`."
        " Leave empty for module-level code.",
    )

    def __str__(self) -> str:
        return f"{self.path}:{self.start_line}-{self.end_line}"


class Finding(BaseModel):
    """One factual claim about the repository and the lines that back it."""

    claim: str = Field(description="A single, specific claim in one or two sentences.")
    # Not `min_length=1`: one uncited Finding would fail the whole model call. The Code
    # Navigator drops uncited Findings instead.
    citations: list[Citation] = Field(description="At least one line range that shows the claim.")


@dataclass(frozen=True)
class Report:
    """The answer to a Run. The answer text refers to its Findings as [1], [2]."""

    run_id: UUID
    question: str
    snapshot: Snapshot
    answer: str
    findings: list[Finding]
    rejected: list[Citation]
    """The Citations the verifier dropped."""
    quarantined: list[str]
    """The Quarantined chunks the Tools hid from the model, e.g. `app/auth.py:14-15 login`."""
    calls: list[ModelCall]
    duration_s: float

    def __str__(self) -> str:
        lines = [f"Snapshot: {self.snapshot}", f"Question: {self.question}", "", self.answer]
        if self.findings:
            lines.append("")
        for number, finding in enumerate(self.findings, 1):
            lines.append(f"[{number}] {finding.claim}")
            lines.extend(f"    {citation}" for citation in finding.citations)
        if self.quarantined:
            lines.extend(["", "Quarantined as a possible prompt injection:"])
            lines.extend(f"    {chunk}" for chunk in self.quarantined)
        lines.extend(["", self._usage()])
        return "\n".join(lines)

    def _usage(self) -> str:
        """E.g. `2 calls · 3,120 in / 410 out tokens · 21.6s`."""
        if not self.calls:
            return f"No model calls · {self.duration_s:.1f}s"
        calls = f"{len(self.calls)} call{'' if len(self.calls) == 1 else 's'}"
        input_tokens = sum(call.input_tokens for call in self.calls)
        output_tokens = sum(call.output_tokens for call in self.calls)
        tokens = f"{input_tokens:,} in / {output_tokens:,} out tokens"
        return f"{calls} · {tokens} · {self.duration_s:.1f}s"
