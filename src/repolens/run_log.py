"""The run log: one JSON line per event of a Run, so a Run can be inspected after the fact."""

import json
from datetime import UTC, datetime
from pathlib import Path


class RunLog:
    """Appends events to a `.jsonl` file, creating its directory on first use."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, event: str, **fields: object) -> None:
        """Add one event, e.g. `write("call", model=..., input_tokens=...)`."""
        line = {"time": datetime.now(UTC).isoformat(), "event": event, **fields}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as file:
            file.write(json.dumps(line, default=str) + "\n")
