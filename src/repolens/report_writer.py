"""The Report Writer: composes the answer from Findings only."""

from pydantic import BaseModel, Field

from repolens.llm import LLM
from repolens.report import Finding

SYSTEM_PROMPT = """\
You are the Report Writer for a repository question-answering tool.
Answer the question in a few sentences using only the numbered findings. After each \
sentence, cite the findings it relies on as [1], [2]. Don't add facts, numbers or file \
names that aren't in the findings."""


class ReportDraft(BaseModel):
    """The answer to the question, citing findings by number."""

    answer: str = Field(description="A short answer that cites findings as [1], [2].")


def write_answer(question: str, findings: list[Finding], llm: LLM) -> str:
    """Answer the question from the Findings alone, citing them by number."""
    numbered = "\n".join(f"[{i}] {finding.claim}" for i, finding in enumerate(findings, 1))
    user = f"Question: {question}\n\nFindings:\n{numbered}"
    return llm.structured(SYSTEM_PROMPT, user, ReportDraft).value.answer
