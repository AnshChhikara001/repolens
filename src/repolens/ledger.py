"""The cost ledger: one row per model call, kept in Postgres (ADR-0002, ADR-0004)."""

from collections.abc import Sequence
from uuid import UUID

import psycopg

from repolens.costs import ModelCall
from repolens.snapshot import Snapshot

SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger (
    id bigserial PRIMARY KEY,
    run_id uuid NOT NULL,
    snapshot_id text NOT NULL,
    model text NOT NULL,
    input_tokens integer NOT NULL,
    output_tokens integer NOT NULL,
    cost_usd double precision NOT NULL,
    shadow boolean NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ledger_run_id_idx ON ledger (run_id);
"""


class Ledger:
    """What every model call cost, by Run. Rows are kept when a Run fails."""

    def __init__(self, url: str) -> None:
        self.url = url

    def setup(self) -> None:
        """Create the table if it doesn't exist yet."""
        with psycopg.connect(self.url) as conn:
            conn.execute(SCHEMA)

    def record(self, run_id: UUID, snapshot: Snapshot, calls: Sequence[ModelCall]) -> None:
        """Add a Run's model calls."""
        with psycopg.connect(self.url) as conn, conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO ledger (run_id, snapshot_id, model, input_tokens, output_tokens,"
                " cost_usd, shadow) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                [
                    (
                        run_id,
                        str(snapshot),
                        c.model,
                        c.input_tokens,
                        c.output_tokens,
                        c.cost_usd,
                        c.shadow,
                    )
                    for c in calls
                ],
            )

    def calls(self, run_id: UUID) -> list[ModelCall]:
        """The model calls of one Run, in the order they were made."""
        with psycopg.connect(self.url) as conn:
            rows = conn.execute(
                "SELECT model, input_tokens, output_tokens, cost_usd, shadow FROM ledger"
                " WHERE run_id = %s ORDER BY id",
                (run_id,),
            ).fetchall()
        return [ModelCall(*row) for row in rows]

    def total_usd(self) -> float:
        """What every recorded call has cost, including Shadow cost."""
        with psycopg.connect(self.url) as conn:
            row = conn.execute("SELECT coalesce(sum(cost_usd), 0) FROM ledger").fetchone()
        return float(row[0]) if row else 0.0
