"""Postgres storage for Snapshots and their embedded Chunks."""

from collections.abc import Collection, Sequence
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

-- Full-text search over path segments, symbol parts and code. Dots and slashes split
-- `app/auth.py` and `LoginService.login` into words; the parser already splits `_`.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS search tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('english', translate(path || ' ' || symbol, '/.', '  ')), 'A')
    || setweight(to_tsvector('english', translate(content, '/.', '  ')), 'B')
) STORED;

CREATE INDEX IF NOT EXISTS chunks_search_idx ON chunks USING gin (search);
""").format(dimensions=sql.Literal(EMBEDDING_DIMENSIONS))

# Reciprocal rank fusion of a keyword and a vector ranking, both limited to one Snapshot.
# Keyword terms are OR-ed so a question matches chunks that contain any of its words.
# Vectors are compared exactly: a Snapshot has at most a few thousand chunks, and an
# approximate index would filter by Snapshot after the search and lose results.
SEARCH = """
WITH query AS (
    SELECT replace(
        plainto_tsquery('english', translate(%(text)s, '/.', '  '))::text, '&', '|'
    )::tsquery AS terms
),
keyword AS (
    SELECT id, row_number() OVER (ORDER BY ts_rank_cd(search, terms) DESC, id) AS rank
    FROM chunks, query
    WHERE snapshot_id = %(snapshot)s AND search @@ terms
),
semantic AS (
    SELECT id, row_number() OVER (ORDER BY embedding <=> %(embedding)s::vector, id) AS rank
    FROM chunks
    WHERE snapshot_id = %(snapshot)s
)
SELECT path, start_line, end_line, symbol, content
FROM keyword FULL JOIN semantic USING (id) JOIN chunks USING (id)
ORDER BY coalesce(1.0 / (%(k)s + keyword.rank), 0)
    + coalesce(1.0 / (%(k)s + semantic.rank), 0) DESC, id
LIMIT %(limit)s
"""
RRF_K = 60


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
                            _vector(embedding),
                        )
                    )

    def chunks(self, snapshot: Snapshot, paths: Collection[str] | None = None) -> list[Chunk]:
        """Return a Snapshot's Chunks, or only those of the given files."""
        with psycopg.connect(self.url) as conn:
            rows = conn.execute(
                "SELECT path, start_line, end_line, symbol, content FROM chunks"
                " WHERE snapshot_id = %(snapshot)s"
                " AND (%(paths)s::text[] IS NULL OR path = ANY(%(paths)s))"
                " ORDER BY path, start_line",
                {"snapshot": str(snapshot), "paths": None if paths is None else list(paths)},
            ).fetchall()
        return [Chunk(*row) for row in rows]

    def search(
        self, snapshot: Snapshot, text: str, embedding: Sequence[float], limit: int
    ) -> list[Chunk]:
        """Return the Chunks that best match a question by keywords and by meaning."""
        params = {
            "snapshot": str(snapshot),
            "text": text,
            "embedding": _vector(embedding),
            "k": RRF_K,
            "limit": limit,
        }
        with psycopg.connect(self.url) as conn:
            rows = conn.execute(SEARCH, params).fetchall()
        return [Chunk(*row) for row in rows]


def _vector(embedding: Sequence[float]) -> str:
    return f"[{','.join(map(str, embedding))}]"
