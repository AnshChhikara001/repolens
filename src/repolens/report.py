"""Findings, Citations and the Report a Run returns (ADR-0007)."""

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, Field

from repolens.costs import ModelCall
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
    calls: list[ModelCall]

    @property
    def cost_usd(self) -> float:
        return sum(call.cost_usd for call in self.calls)

    def __str__(self) -> str:
        lines = [f"Snapshot: {self.snapshot}", f"Question: {self.question}", "", self.answer]
        if self.findings:
            lines.append("")
        for number, finding in enumerate(self.findings, 1):
            lines.append(f"[{number}] {finding.claim}")
            lines.extend(f"    {citation}" for citation in finding.citations)
        lines.extend(["", self._cost()])
        return "\n".join(lines)

    def _cost(self) -> str:
        calls = f"{len(self.calls)} model call{'' if len(self.calls) == 1 else 's'}"
        shadow = ", at shadow prices" if any(call.shadow for call in self.calls) else ""
        return f"Cost: ${self.cost_usd:.4f} for {calls}{shadow}"
