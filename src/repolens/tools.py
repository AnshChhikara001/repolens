"""The Tools the Code Navigator uses to look at a Snapshot: search, read lines, find definitions.

Every excerpt a Tool shows the model goes into the Lines read, cut to the lines shown and named
after the Chunk around it, so the verifier accepts Citations to exactly those lines (ADR-0007).
Excerpts the model has already seen are listed instead of shown again, and a Tool result and a
whole Run show at most a fixed number of lines, so the prompt stays bounded.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace

from repolens.chunking import Chunk
from repolens.embedding import Embedder
from repolens.lines_read import LinesRead
from repolens.rerank import Reranker, rerank
from repolens.snapshot import Snapshot
from repolens.store import ChunkStore

# Hybrid search finds the candidates, the cross-encoder keeps the best few for the prompt.
# Without a reranker, the prompt gets the first few in search order.
CANDIDATES = 24
TOP_K = 6
MAX_DEFINITIONS = 4
MAX_RESULT_LINES = 500
MAX_RUN_LINES = 1_500


@dataclass(frozen=True)
class ToolResult:
    """What a Tool shows the model, and the excerpts in it."""

    text: str
    shown: list[Chunk]


class Tools:
    """The Tools of one Run. They add every excerpt they show to `lines_read`."""

    def __init__(
        self,
        snapshot: Snapshot,
        embedder: Embedder,
        store: ChunkStore,
        reranker: Reranker | None,
        lines_read: LinesRead,
    ) -> None:
        self._snapshot = snapshot
        self._embedder = embedder
        self._store = store
        self._reranker = reranker
        self._lines_read = lines_read
        self._lines_shown = 0

    def search_code(self, query: str) -> ToolResult:
        """The code that best matches the query by keywords and by meaning."""
        [embedding] = self._embedder.embed([query])
        if self._reranker is None:
            chunks = self._store.search(self._snapshot, query, embedding, TOP_K)
        else:
            candidates = self._store.search(self._snapshot, query, embedding, CANDIDATES)
            chunks = rerank(query, candidates, self._reranker, TOP_K)
        return self._show(chunks) if chunks else ToolResult(f"No code matches {query!r}.", [])

    def read_lines(self, path: str, start_line: int, end_line: int) -> ToolResult:
        """Lines of one file. Without a valid end line, as many lines as one result may show."""
        chunks = self._store.chunks(self._snapshot, [path])
        if not chunks:
            return ToolResult(f"There is no file {path!r} in {self._snapshot}.", [])
        start_line = max(start_line, 1)
        if end_line < start_line:
            end_line = start_line + MAX_RESULT_LINES - 1
        excerpts = [
            _cut(chunk, max(start_line, chunk.start_line), min(end_line, chunk.end_line))
            for chunk in chunks
            if chunk.start_line <= end_line and start_line <= chunk.end_line
        ]
        if not excerpts:
            last = chunks[-1].end_line
            return ToolResult(
                f"{path} has no code in lines {start_line}-{end_line}"
                f" (its code ends at line {last}).",
                [],
            )
        return self._show(excerpts)

    def find_definition(self, name: str) -> ToolResult:
        """Where a function, class or method is defined, e.g. `login` or `LoginService.login`."""
        chunks = self._store.definitions(self._snapshot, name, MAX_DEFINITIONS)
        return self._show(chunks) if chunks else ToolResult(f"No definition of {name!r}.", [])

    def _show(self, chunks: Sequence[Chunk]) -> ToolResult:
        """Show the excerpts not seen yet, up to the line limits, and record them as read."""
        shown: list[Chunk] = []
        seen: list[Chunk] = []
        notes: list[str] = []
        budget = min(MAX_RESULT_LINES, MAX_RUN_LINES - self._lines_shown)
        for chunk in chunks:
            if self._lines_read.covers(chunk.path, chunk.start_line, chunk.end_line):
                seen.append(chunk)
                continue
            if budget <= 0:
                notes.append(_limit_note(self._lines_shown))
                break
            if chunk.end_line - chunk.start_line + 1 > budget:
                chunk = _cut(chunk, chunk.start_line, chunk.start_line + budget - 1)
                notes.append(f"{chunk.path} was cut after line {chunk.end_line}.")
            shown.append(chunk)
            budget -= chunk.end_line - chunk.start_line + 1
            self._lines_shown += chunk.end_line - chunk.start_line + 1
        self._lines_read.add(shown)
        parts = [excerpt(chunk) for chunk in shown]
        if seen:
            parts.append("Already shown above: " + ", ".join(label(c) for c in seen))
        return ToolResult("\n\n".join(parts + notes), shown)


def excerpt(chunk: Chunk) -> str:
    """The excerpt as the model sees it: every line starts with its number."""
    lines = "\n".join(
        f"{number} {line}" for number, line in enumerate(chunk.text.split("\n"), chunk.start_line)
    )
    return f'<code path="{chunk.path}" symbol="{chunk.symbol}">\n{lines}\n</code>'


def label(chunk: Chunk) -> str:
    """E.g. `app/auth.py:14-15 LoginService.login`."""
    return f"{chunk.path}:{chunk.start_line}-{chunk.end_line} {chunk.symbol}"


def _cut(chunk: Chunk, start_line: int, end_line: int) -> Chunk:
    """The lines from `start_line` to `end_line` of a Chunk, under the Chunk's symbol."""
    lines = chunk.text.split("\n")[start_line - chunk.start_line : end_line - chunk.start_line + 1]
    return replace(chunk, start_line=start_line, end_line=end_line, text="\n".join(lines))


def _limit_note(lines_shown: int) -> str:
    if lines_shown >= MAX_RUN_LINES:
        return (
            f"The Run has shown its limit of {MAX_RUN_LINES} lines. Answer with what you've read."
        )
    return f"This result has reached its limit of {MAX_RESULT_LINES} lines."
