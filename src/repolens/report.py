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
    citations: list[Citation] = Field(description="At least one line range that shows the claim.")


@dataclass(frozen=True)
class Report:
    question: str
    snapshot: Snapshot
    answer: str
    findings: list[Finding]
