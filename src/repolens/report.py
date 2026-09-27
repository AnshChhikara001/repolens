"""Findings, Citations and the Report a Run returns (ADR-0007)."""

from dataclasses import dataclass

from pydantic import BaseModel, Field

from repolens.snapshot import Snapshot


class Citation(BaseModel):
    """A line range in a file at the analysed commit."""

    path: str = Field(description="File path relative to the repository root.")
    start_line: int = Field(description="First cited line, 1-based.")
    end_line: int = Field(description="Last cited line, inclusive.")

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

    question: str
    snapshot: Snapshot
    answer: str
    findings: list[Finding]

    def __str__(self) -> str:
        lines = [f"Snapshot: {self.snapshot}", f"Question: {self.question}", "", self.answer]
        if self.findings:
            lines.append("")
        for number, finding in enumerate(self.findings, 1):
            lines.append(f"[{number}] {finding.claim}")
            lines.extend(f"    {citation}" for citation in finding.citations)
        return "\n".join(lines)
