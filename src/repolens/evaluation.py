"""The eval: pinned questions with the files that answer them, and how well Runs find them.

Each question names a Snapshot by its full commit SHA, so every eval reads the same code.
A Run is scored only by its verified Citations: which expected files (and symbols) they point
into, and how many of the model's Citations the verifier kept.
"""

import re
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from repolens.llm import LLMError, ModelCall
from repolens.report import Report
from repolens.snapshot import RepoRef

# List prices in dollars per 1M input and output tokens, by model name without the provider.
# Only for the eval's cost estimate.
PRICES: dict[str, tuple[float, float]] = {
    "claude-sonnet-5": (2.00, 10.00),
    "gemini-3.1-flash-lite": (0.25, 1.50),
}

_SHA = re.compile(r"[0-9a-f]{40}")


class Question(BaseModel):
    """A question about a pinned Snapshot and where its answer is."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    repo: str = Field(description="`owner/repo@sha` with the full commit SHA.")
    question: str
    expected_files: list[str] = Field(min_length=1)
    expected_symbols: list[str] = []


class _Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[Question]


def load_questions(path: Path) -> list[Question]:
    """Read the questions from a TOML file. Raises ValueError for an invalid dataset."""
    questions = _Dataset.model_validate(tomllib.loads(path.read_text())).questions
    seen: set[str] = set()
    for question in questions:
        ref = RepoRef.parse(question.repo).ref
        if ref is None or not _SHA.fullmatch(ref):
            raise ValueError(f"{question.id}: {question.repo} is not pinned to a full commit SHA")
        if question.id in seen:
            raise ValueError(f"duplicate question id {question.id!r}")
        seen.add(question.id)
    return questions


@dataclass(frozen=True)
class Outcome:
    """A question's Report, or why its Run failed."""

    question: Question
    report: Report | None = None
    error: str | None = None


def evaluate(
    questions: Sequence[Question], run_question: Callable[[Question], Report]
) -> list[Outcome]:
    """Run every question. A failed model call fails only its own question."""
    outcomes: list[Outcome] = []
    for question in questions:
        try:
            outcomes.append(Outcome(question, run_question(question)))
        except (LLMError, TimeoutError) as exc:
            outcomes.append(Outcome(question, error=str(exc)))
    return outcomes


def results_table(outcomes: Sequence[Outcome]) -> str:
    """A markdown summary of the eval, a row per question, and the errors."""
    scores = {o.question.id: _score(o.question, o.report) for o in outcomes if o.report}
    errors = [o for o in outcomes if o.error is not None]
    lines = [
        *_summary(len(outcomes), len(errors), list(scores.values())),
        "",
        "| Question | Files | Symbols | Citations valid | Findings | Model s | Run s"
        " | Tokens in / out | Est. cost |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for outcome in outcomes:
        score = scores.get(outcome.question.id)
        if score is None:
            lines.append(f"| {outcome.question.id} | error |{' |' * 7}")
            continue
        symbols = _fraction(score.symbols_found, score.symbols) if score.symbols else "-"
        lines.append(
            f"| {outcome.question.id} | {_fraction(score.files_found, score.files)} | {symbols}"
            f" | {_fraction(score.valid, score.valid + score.rejected)} | {score.findings}"
            f" | {score.model_s:.1f} | {score.run_s:.1f}"
            f" | {score.input_tokens:,} / {score.output_tokens:,} | {_dollars(score.cost)} |"
        )
    if errors:
        lines.extend(["", "Errors:", *(f"- {o.question.id}: {o.error}" for o in errors)])
    return "\n".join(lines)


@dataclass(frozen=True)
class _Score:
    """What one Report got right, and what it used."""

    files: int
    files_found: int
    symbols: int
    symbols_found: int
    valid: int
    rejected: int
    findings: int
    model_s: float
    run_s: float
    input_tokens: int
    output_tokens: int
    cost: float | None


def _score(question: Question, report: Report) -> _Score:
    citations = [citation for finding in report.findings for citation in finding.citations]
    # A symbol counts only where it was expected: `get_command` in another file is another one.
    expected_symbols = [
        citation.symbol
        for citation in citations
        if citation.symbol and citation.path in question.expected_files
    ]
    return _Score(
        files=len(question.expected_files),
        files_found=len(set(question.expected_files) & {c.path for c in citations}),
        symbols=len(question.expected_symbols),
        symbols_found=sum(
            any(s == expected or s.endswith(f".{expected}") for s in expected_symbols)
            for expected in question.expected_symbols
        ),
        valid=len(citations),
        rejected=len(report.rejected),
        findings=len(report.findings),
        model_s=sum(call.latency_s for call in report.calls),
        run_s=report.duration_s,
        input_tokens=sum(call.input_tokens for call in report.calls),
        output_tokens=sum(call.output_tokens for call in report.calls),
        cost=_cost(report.calls),
    )


def _summary(questions: int, errors: int, scores: list[_Score]) -> list[str]:
    lines = [
        "| Metric | Value |",
        "|---|---|",
        f"| Questions | {questions} ({errors} error{'' if errors == 1 else 's'}) |",
    ]
    if not scores:
        return lines
    valid = sum(s.valid for s in scores)
    cited = valid + sum(s.rejected for s in scores)
    with_symbols = [s for s in scores if s.symbols]
    found_nothing = sum(s.findings == 0 for s in scores)
    costs = [s.cost for s in scores]
    lines += [
        f"| Citation validity | {_fraction(valid, cited)} ({_percent(valid, cited)}) |",
        f"| Expected-file recall | {_mean_percent([s.files_found / s.files for s in scores])} |",
    ]
    if with_symbols:
        recall = _mean_percent([s.symbols_found / s.symbols for s in with_symbols])
        count = f"{len(with_symbols)} question{'' if len(with_symbols) == 1 else 's'}"
        lines.append(f"| Expected-symbol recall | {recall} ({count}) |")
    lines += [
        f"| Found nothing | {found_nothing}/{len(scores)} ({_percent(found_nothing, len(scores))})"
        " |",
        f"| Model latency | {_mean([s.model_s for s in scores]):.1f}s mean |",
        f"| Run time | {_mean([s.run_s for s in scores]):.1f}s mean |",
        f"| Tokens | {_mean([s.input_tokens for s in scores]):,.0f} in"
        f" / {_mean([s.output_tokens for s in scores]):,.0f} out mean |",
    ]
    if None in costs:
        lines.append("| Est. cost | - |")
    else:
        total = sum(c for c in costs if c is not None)
        lines.append(f"| Est. cost | ${total / len(costs):.4f} mean, ${total:.4f} total |")
    return lines


def _cost(calls: Sequence[ModelCall]) -> float | None:
    """The calls' cost at list prices, or None if a model has no known price."""
    total = 0.0
    for call in calls:
        price = PRICES.get(call.model.partition(":")[2])
        if price is None:
            return None
        total += (call.input_tokens * price[0] + call.output_tokens * price[1]) / 1_000_000
    return total


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _fraction(part: int, whole: int) -> str:
    return f"{part}/{whole}"


def _percent(part: int, whole: int) -> str:
    return f"{part / whole:.0%}" if whole else "-"


def _mean_percent(values: Sequence[float]) -> str:
    return f"{_mean(values):.0%}"


def _dollars(amount: float | None) -> str:
    return "-" if amount is None else f"${amount:.4f}"
