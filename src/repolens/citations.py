"""The citation verifier: checks every Citation against the Snapshot (ADR-0007)."""

import re
from collections import defaultdict
from collections.abc import Sequence

from repolens.chunking import Chunk
from repolens.report import Citation, Finding
from repolens.snapshot import Snapshot
from repolens.store import ChunkStore

# Keywords that define a name in Python or TypeScript.
_DEFINITION = r"(?:def|class|function|interface|type|enum|const|let|var)\s+{name}(?!\w)"


def verify(findings: Sequence[Finding], snapshot: Snapshot, store: ChunkStore) -> list[Finding]:
    """Drop the Citations the Snapshot doesn't back, then the Findings left uncited."""
    paths = {citation.path for finding in findings for citation in finding.citations}
    by_path: defaultdict[str, list[Chunk]] = defaultdict(list)
    for chunk in store.chunks(snapshot, paths) if paths else []:
        by_path[chunk.path].append(chunk)
    verified: list[Finding] = []
    for finding in findings:
        citations = [c for c in finding.citations if _valid(c, by_path[c.path])]
        if citations:
            verified.append(Finding(claim=finding.claim, citations=citations))
    return verified


def _valid(citation: Citation, chunks: list[Chunk]) -> bool:
    """The file was ingested, the lines are in it, and the symbol is defined there.

    Each dotted part of the symbol must name one Chunk that overlaps the lines, or be
    defined in it, so `LoginService.login` matches a method inside a class Chunk.
    """
    if not chunks:
        return False
    last_line = max(chunk.end_line for chunk in chunks)
    if not 1 <= citation.start_line <= citation.end_line <= last_line:
        return False
    if citation.symbol is None:
        return True
    parts = citation.symbol.split(".")
    return any(
        all(_names(chunk, part) for part in parts)
        for chunk in chunks
        if chunk.start_line <= citation.end_line and citation.start_line <= chunk.end_line
    )


def _names(chunk: Chunk, name: str) -> bool:
    definition = _DEFINITION.format(name=re.escape(name))
    return name in chunk.symbol.split(".") or re.search(definition, chunk.text) is not None
