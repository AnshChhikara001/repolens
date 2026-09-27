"""The Report Writer Specialist: composes the answer from Findings only."""

from typing import cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from repolens.report import Finding

SYSTEM_PROMPT = """\
You are the Report Writer for a repository question-answering tool.
Answer the question in a few sentences using only the numbered findings. After each \
sentence, cite the findings it relies on as [1], [2]. Don't add facts, numbers or file \
names that aren't in the findings."""


class ReportDraft(BaseModel):
    """The answer to the question, citing findings by number."""

    answer: str = Field(description="A short answer that cites findings as [1], [2].")


def write_answer(question: str, findings: list[Finding], model: BaseChatModel) -> str:
    numbered = "\n".join(f"[{i}] {finding.claim}" for i, finding in enumerate(findings, 1))
    result = model.with_structured_output(ReportDraft).invoke(
        [
            SystemMessage(SYSTEM_PROMPT),
            HumanMessage(f"Question: {question}\n\nFindings:\n{numbered}"),
        ]
    )
    return cast(ReportDraft, result).answer
