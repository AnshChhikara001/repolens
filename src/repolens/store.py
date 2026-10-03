"""Postgres storage for Snapshots and their embedded Chunks."""

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass

import psycopg
from psycopg import sql

from repolens.chunking import DEFINITION_PATTERN, Chunk
from repolens.embedding import EMBEDDING_DIMENSIONS
from repolens.snapshot import Snapshot

SCHEMA_LOCK = 7_365_210  # any number no other code uses as an advisory lock

SCHEMA = sql.SQL("""
-- Two processes changing the schema at once can deadlock, so they take turns.
SELECT pg_advisory_xact_lock({lock});

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

-- Snapshots stored before index versions get '', which matches no version.
ALTER TABLE snapshots ADD COLUMN IF NOT EXISTS index_version text NOT NULL DEFAULT '';

-- Full-text search over path segments, symbol parts and code. Dots and slashes split
-- `app/auth.py` and `LoginService.login` into words; the parser already splits `_`.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS search tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('english', translate(path || ' ' || symbol, '/.', '  ')), 'A')
    || setweight(to_tsvector('english', translate(content, '/.', '  ')), 'B')
) STORED;

CREATE INDEX IF NOT EXISTS chunks_search_idx ON chunks USING gin (search);
""").format(dimensions=sql.Literal(EMBEDDING_DIMENSIONS), lock=sql.Literal(SCHEMA_LOCK))

# Reciprocal rank fusion of a keyword and a vector ranking, both limited to one Snapshot.
# Keyword terms are OR-ed so a question matches chunks that contain any of its words.
# Vectors are compared exactly: a Snapshot has at most a few thousand chunks, and an
# approximate index would filter by Snapshot after the search and lose results.
# Tests can come last: they use a question's words more than the code that does the work.
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
ORDER BY %(tests_last)s AND path ~ %(test_path)s,
    coalesce(1.0 / (%(k)s + keyword.rank), 0)
    + coalesce(1.0 / (%(k)s + semantic.rank), 0) DESC, id
LIMIT %(limit)s
"""
RRF_K = 60

# Files in a test folder, or named like a test in Python, JavaScript/TypeScript or Go. The
# same pattern works in Python and in Postgres.
TEST_PATH = (
    r"(^|/)(tests?|__tests__)/|(^|/)(test_[^/]*\.py|conftest\.py)$"
    r"|\.(test|spec)\.[a-z]+$|_test\.go$"
)
# The word test or spec in any form, as in `test_login`, but not `latest` or `TestClient`.
MENTIONS_TESTS = re.compile(r"(?<![A-Za-z])([Tt]est(s|ing|ed)?|[Ss]pecs?)(?![A-Za-z])")

# Chunks named after a symbol come first, then Chunks that define it inside, like a method
# in a class that wasn't split.
FIND_DEFINITIONS = """
SELECT path, start_line, end_line, symbol, content
FROM chunks
WHERE snapshot_id = %(snapshot)s AND (symbol ~ %(symbol)s OR content ~ %(definition)s)
ORDER BY symbol ~ %(symbol)s DESC, path, start_line
LIMIT %(limit)s
"""


class SnapshotExistsError(Exception):
    """The Snapshot was stored by someone else first."""


@dataclass(frozen=True)
class StoredSnapshot:
    file_count: int
    chunk_count: int
    index_version: str


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
                "SELECT file_count, chunk_count, index_version FROM snapshots WHERE id = %s",
                (str(snapshot),),
            ).fetchone()
        return StoredSnapshot(*row) if row else None

    def delete(self, snapshot: Snapshot) -> None:
        """Remove a Snapshot and its Chunks."""
        with psycopg.connect(self.url) as conn:
            conn.execute("DELETE FROM snapshots WHERE id = %s", (str(snapshot),))

    def save(
        self,
        snapshot: Snapshot,
        files: int,
        chunks: Sequence[Chunk],
        embeddings: Sequence[Sequence[float]],
        model: str,
        index_version: str,
    ) -> None:
        """Store a Snapshot and all its Chunks in one transaction.

        Raises SnapshotExistsError if the Snapshot is already stored.
        """
        with psycopg.connect(self.url) as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO snapshots (id, owner, name, sha, embedding_model, index_version,"
                    " file_count, chunk_count) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        str(snapshot),
                        snapshot.owner,
                        snapshot.name,
                        snapshot.sha,
                        model,
                        index_version,
                        files,
                        len(chunks),
                    ),
                )
            except psycopg.errors.UniqueViolation as exc:
                raise SnapshotExistsError(str(snapshot)) from exc
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
        """Return the Chunks that best match a question by keywords and by meaning.

        Tests come after the rest of the code, unless the question mentions tests.
        """
        params = {
            "snapshot": str(snapshot),
            "text": text,
            "embedding": _vector(embedding),
            "tests_last": not MENTIONS_TESTS.search(text),
            "test_path": TEST_PATH,
            "k": RRF_K,
            "limit": limit,
        }
        with psycopg.connect(self.url) as conn:
            rows = conn.execute(SEARCH, params).fetchall()
        return [Chunk(*row) for row in rows]

    def definitions(self, snapshot: Snapshot, name: str, limit: int) -> list[Chunk]:
        """Return the Chunks that define a name like `login` or `LoginService.login`.

        A TypeScript private name matches with or without its `#`.
        """
        parts = [re.escape(part.removeprefix("#")) for part in name.split(".")]
        params = {
            "snapshot": str(snapshot),
            "symbol": r"(^|\.)#?" + r"\.#?".join(parts) + "$",
            "definition": DEFINITION_PATTERN.format(name="#?" + parts[-1]),
            "limit": limit,
        }
        with psycopg.connect(self.url) as conn:
            rows = conn.execute(FIND_DEFINITIONS, params).fetchall()
        return [Chunk(*row) for row in rows]


def _vector(embedding: Sequence[float]) -> str:
    return f"[{','.join(map(str, embedding))}]"
