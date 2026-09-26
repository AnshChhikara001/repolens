import os

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from repolens.store import ChunkStore

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://repolens:repolens@localhost:5432/repolens_test"
)


def create_database(url: str) -> None:
    name = str(conninfo_to_dict(url)["dbname"])
    with psycopg.connect(make_conninfo(url, dbname="postgres"), autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


@pytest.fixture
def store() -> ChunkStore:
    """An empty store in a separate test database. Skipped locally when Postgres is down."""
    try:
        create_database(TEST_DATABASE_URL)
    except psycopg.OperationalError as exc:
        if os.environ.get("CI"):
            raise
        pytest.skip(f"Postgres is not running: {exc}")
    store = ChunkStore(TEST_DATABASE_URL)
    store.setup()
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        conn.execute("TRUNCATE snapshots CASCADE")
    return store
