"""The citation verifier: checks every Citation against the lines read (ADR-0007)."""

import re
from collections.abc import Sequence

from repolens.chunking import Chunk
from repolens.lines_read import LinesRead
from repolens.report import Citation, Finding

# Keywords that define a name in Python or TypeScript.
_DEFINITION = r"(?:def|class|function|interface|type|enum|const|let|var)\s+{name}(?!\w)"


def verify(
    findings: Sequence[Finding], lines_read: LinesRead
) -> tuple[list[Finding], list[Citation]]:
    """Drop the Citations to lines the model wasn't shown, then the Findings left uncited.

    Returns the verified Findings and the rejected Citations.
    """
    verified: list[Finding] = []
    rejected: list[Citation] = []
    for finding in findings:
        citations: list[Citation] = []
        for citation in finding.citations:
            (citations if _valid(citation, lines_read) else rejected).append(citation)
        if citations:
            verified.append(Finding(claim=finding.claim, citations=citations))
    return verified, rejected


def _valid(citation: Citation, lines_read: LinesRead) -> bool:
    """Every cited line was shown, and the symbol is defined there.

    Each dotted part of the symbol must name an excerpt that overlaps the lines, or be
    defined in it, so `LoginService.login` matches a method inside a class excerpt.
    """
    if not lines_read.covers(citation.path, citation.start_line, citation.end_line):
        return False
    if citation.symbol is None:
        return True
    parts = citation.symbol.split(".")
    return any(
        all(_names(excerpt, part) for part in parts)
        for excerpt in lines_read.overlapping(citation.path, citation.start_line, citation.end_line)
    )


def _names(excerpt: Chunk, name: str) -> bool:
    definition = _DEFINITION.format(name=re.escape(name))
    return name in excerpt.symbol.split(".") or re.search(definition, excerpt.text) is not None
