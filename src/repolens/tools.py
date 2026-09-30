"""The Tools the Code Navigator uses to look at a Snapshot: search, read lines, find definitions.

Every excerpt a Tool shows the model goes into the Lines read, cut to the lines shown and named
after the Chunk around it, so the verifier accepts Citations to exactly those lines (ADR-0007).
Excerpts the model has already seen are listed instead of shown again, and a Tool result and a
whole Run show at most a fixed number of lines, so the prompt stays bounded. The hits of a
search or a definition lookup share their result's lines, so each shows at least its first
lines; the model reads the rest with `read_lines`.
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
        return (
            self._show(chunks, share=True)
            if chunks
            else ToolResult(f"No code matches {query!r}.", [])
        )

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
            return ToolResult(
                f"{path} has no code in lines {start_line}-{end_line}."
                f" Its code is in lines {chunks[0].start_line}-{chunks[-1].end_line}.",
                [],
            )
        return self._show(excerpts)

    def find_definition(self, name: str) -> ToolResult:
        """Where a function, class or method is defined, e.g. `login` or `LoginService.login`."""
        name = name.strip().removesuffix("()")
        chunks = self._store.definitions(self._snapshot, name, MAX_DEFINITIONS)
        return (
            self._show(chunks, share=True)
            if chunks
            else ToolResult(f"No definition of {name!r}.", [])
        )

    def _show(self, chunks: Sequence[Chunk], share: bool = False) -> ToolResult:
        """Show the lines of the excerpts not seen yet, up to the line limits, and record them.

        Excerpts fill the limit in order, like the lines of one file. The hits of a search or
        a definition lookup `share` it instead, so each shows at least its first lines.
        """
        new: list[Chunk] = []
        seen: list[Chunk] = []
        for chunk in chunks:
            start_line = self._lines_read.first_unread(chunk.path, chunk.start_line, chunk.end_line)
            if start_line is None:
                seen.append(chunk)
            else:
                new.append(_cut(chunk, start_line, chunk.end_line))
        budget = min(MAX_RESULT_LINES, MAX_RUN_LINES - self._lines_shown)
        sizes = [_length(chunk) for chunk in new]
        limits = _share(sizes, budget) if share else _fill(sizes, budget)
        self._lines_shown += sum(limits)
        shown: list[Chunk] = []
        parts: list[str] = []
        for chunk, limit in zip(new, limits, strict=True):
            if limit == 0:
                continue
            part = _cut(chunk, chunk.start_line, chunk.start_line + limit - 1)
            shown.append(part)
            parts.append(excerpt(part))
            if part.end_line < chunk.end_line:
                parts.append(
                    f"{chunk.path} was cut after line {part.end_line}. Read lines"
                    f" {part.end_line + 1}-{chunk.end_line} for the rest of {chunk.symbol}."
                )
        self._lines_read.add(shown)
        if seen:
            parts.append("Already shown above: " + ", ".join(label(c) for c in seen))
        dropped = [chunk for chunk, limit in zip(new, limits, strict=True) if limit == 0]
        if dropped or self._lines_shown >= MAX_RUN_LINES:
            parts.append(_limit_note(self._lines_shown))
        if dropped:
            parts.append("Not shown: " + ", ".join(label(c) for c in dropped))
        return ToolResult("\n\n".join(parts), shown)


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


def _length(chunk: Chunk) -> int:
    return chunk.end_line - chunk.start_line + 1


def _fill(sizes: list[int], budget: int) -> list[int]:
    """How many lines each excerpt shows when each in turn takes all it needs."""
    limits: list[int] = []
    for size in sizes:
        limits.append(min(size, budget))
        budget -= limits[-1]
    return limits


def _share(sizes: list[int], budget: int) -> list[int]:
    """How many lines each excerpt shows when they share the budget evenly.

    An excerpt shorter than its share leaves the rest to the longer ones. With fewer lines
    left than excerpts, the first excerpts take them.
    """
    if budget < len(sizes):
        return _fill(sizes, budget)
    limits = [0] * len(sizes)
    shortest_first = sorted(range(len(sizes)), key=lambda i: sizes[i])
    for done, i in enumerate(shortest_first):
        limits[i] = min(sizes[i], budget // (len(sizes) - done))
        budget -= limits[i]
    return limits


def _limit_note(lines_shown: int) -> str:
    if lines_shown >= MAX_RUN_LINES:
        return (
            f"The Run has shown its limit of {MAX_RUN_LINES} lines. Answer with what you've read."
        )
    return f"This result has reached its limit of {MAX_RESULT_LINES} lines."
