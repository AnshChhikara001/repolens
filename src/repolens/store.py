"""Postgres storage for Snapshots and their embedded Chunks."""

from collections.abc import Sequence
from dataclasses import dataclass

import psycopg
from psycopg import sql

from repolens.chunking import Chunk
from repolens.embedding import EMBEDDING_DIMENSIONS
from repolens.snapshot import Snapshot

SCHEMA = sql.SQL("""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS snapshots (
    id text PRIMARY KEY,
    owner text NOT NULL,
    name text NOT NULL,
    sha text NOT NULL,
    embedding_model text NOT NULL,
    file_count integer NOT NULL,
    chunk_count integer NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id bigserial PRIMARY KEY,
    snapshot_id text NOT NULL REFERENCES snapshots (id) ON DELETE CASCADE,
    path text NOT NULL,
    start_line integer NOT NULL,
    end_line integer NOT NULL,
    symbol text NOT NULL,
    content text NOT NULL,
    embedding vector({dimensions}) NOT NULL
);

CREATE INDEX IF NOT EXISTS chunks_snapshot_id_idx ON chunks (snapshot_id);
""").format(dimensions=sql.Literal(EMBEDDING_DIMENSIONS))


@dataclass(frozen=True)
class StoredSnapshot:
    file_count: int
    chunk_count: int


class ChunkStore:
    def __init__(self, url: str) -> None:
        self.url = url

    def setup(self) -> None:
        """Create the tables if they don't exist yet."""
        with psycopg.connect(self.url) as conn:
            conn.execute(SCHEMA)

    def find(self, snapshot: Snapshot) -> StoredSnapshot | None:
        with psycopg.connect(self.url) as conn:
            row = conn.execute(
                "SELECT file_count, chunk_count FROM snapshots WHERE id = %s", (str(snapshot),)
            ).fetchone()
        return StoredSnapshot(row[0], row[1]) if row else None

    def save(
        self,
        snapshot: Snapshot,
        files: int,
        chunks: Sequence[Chunk],
        embeddings: Sequence[Sequence[float]],
        model: str,
    ) -> None:
        """Store a Snapshot and all its Chunks in one transaction."""
        with psycopg.connect(self.url) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO snapshots (id, owner, name, sha, embedding_model, file_count,"
                " chunk_count) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    str(snapshot),
                    snapshot.owner,
                    snapshot.name,
                    snapshot.sha,
                    model,
                    files,
                    len(chunks),
                ),
            )
            with cur.copy(
                "COPY chunks (snapshot_id, path, start_line, end_line, symbol, content, embedding)"
                " FROM STDIN"
            ) as copy:
                for chunk, embedding in zip(chunks, embeddings, strict=True):
                    copy.write_row(
                        (
                            str(snapshot),
                            chunk.path,
                            chunk.start_line,
                            chunk.end_line,
                            chunk.symbol,
                            chunk.text,
                            f"[{','.join(map(str, embedding))}]",
                        )
                    )

    def chunks(self, snapshot: Snapshot) -> list[Chunk]:
        with psycopg.connect(self.url) as conn:
            rows = conn.execute(
                "SELECT path, start_line, end_line, symbol, content FROM chunks"
                " WHERE snapshot_id = %s ORDER BY path, start_line",
                (str(snapshot),),
            ).fetchall()
        return [Chunk(*row) for row in rows]
