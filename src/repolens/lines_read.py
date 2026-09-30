"""Lines read: the lines of each file the model was shown during a Run."""

from collections.abc import Iterable

from repolens.chunking import Chunk


class LinesRead:
    """Every excerpt shown to the model, however it was fetched.

    The citation verifier accepts only Citations to these lines (ADR-0007).
    """

    def __init__(self) -> None:
        self.excerpts: list[Chunk] = []

    def add(self, excerpts: Iterable[Chunk]) -> None:
        self.excerpts.extend(excerpts)

    def covers(self, path: str, start_line: int, end_line: int) -> bool:
        """Whether every line from `start_line` to `end_line` was shown."""
        return start_line <= end_line and self.first_unread(path, start_line, end_line) is None

    def first_unread(self, path: str, start_line: int, end_line: int) -> int | None:
        """The first line from `start_line` to `end_line` that wasn't shown, if any."""
        lines = {
            line
            for excerpt in self.excerpts
            if excerpt.path == path
            for line in range(excerpt.start_line, excerpt.end_line + 1)
        }
        return next((line for line in range(start_line, end_line + 1) if line not in lines), None)

    def overlapping(self, path: str, start_line: int, end_line: int) -> list[Chunk]:
        """The excerpts that show at least one of the lines."""
        return [
            excerpt
            for excerpt in self.excerpts
            if excerpt.path == path
            and excerpt.start_line <= end_line
            and start_line <= excerpt.end_line
        ]
