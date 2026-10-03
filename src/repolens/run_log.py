"""The run log: one JSON line per event of a Run, so a Run can be inspected after the fact."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

type OnEvent = Callable[[dict[str, object]], None]


class RunLog:
    """Appends events to a `.jsonl` file, creating its directory on first use.

    `on_event`, if given, gets each event as it is written, as the log will read it back.
    """

    def __init__(self, path: Path, on_event: OnEvent | None = None) -> None:
        self.path = path
        self._on_event = on_event

    def write(self, event: str, **fields: object) -> None:
        """Add one event, e.g. `write("call", model=..., input_tokens=...)`."""
        line = {"time": datetime.now(UTC).isoformat(), "event": event, **fields}
        text = json.dumps(line, default=str)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as file:
            file.write(text + "\n")
        if self._on_event is not None:
            self._on_event(json.loads(text))
