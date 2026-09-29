from pathlib import Path

import psycopg
import pytest
from conftest import TEST_DATABASE_URL
from fakes import SHA, FakeEmbedder, FixtureSource

from repolens import chunking
from repolens.ingest import IngestError, IngestResult, ingest
from repolens.snapshot import RepoRef, Snapshot
from repolens.store import ChunkStore

REPO = RepoRef("acme", "shop", "main")


def test_ingest_stores_a_chunk_per_definition_in_source_files(store: ChunkStore) -> None:
    result = ingest(REPO, FixtureSource(), FakeEmbedder(), store)

    snapshot = Snapshot("acme", "shop", SHA)
    assert result == IngestResult(snapshot, file_count=5, chunk_count=6, created=True)
    assert {(c.path, c.start_line, c.end_line, c.symbol) for c in store.chunks(snapshot)} == {
        ("app/auth.py", 1, 7, "hash_password"),
        ("app/auth.py", 10, 15, "LoginService"),
        ("app/build/steps.py", 1, 2, "compile_assets"),
        ("web/src/api.ts", 1, 3, "Session"),
        ("web/src/api.ts", 5, 8, "fetchSession"),
        ("web/src/App.tsx", 1, 1, "App"),
    }


def test_reingesting_a_snapshot_does_nothing(store: ChunkStore) -> None:
    ingest(REPO, FixtureSource(), FakeEmbedder(), store)
    source, embedder = FixtureSource(), FakeEmbedder()

    result = ingest(REPO, source, embedder, store)

    assert result == IngestResult(
        Snapshot("acme", "shop", SHA), file_count=5, chunk_count=6, created=False
    )
    assert source.downloads == 0
    assert embedder.texts == []


class OtherEmbedder(FakeEmbedder):
    model = "other-embedding"


def test_a_new_embedding_model_means_ingesting_again(store: ChunkStore) -> None:
    ingest(REPO, FixtureSource(), FakeEmbedder(), store)
    source = FixtureSource()

    result = ingest(REPO, source, OtherEmbedder(), store)

    assert result.created
    assert source.downloads == 1
    assert len(store.chunks(result.snapshot)) == result.chunk_count


def test_a_new_chunker_version_means_ingesting_again(
    store: ChunkStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    ingest(REPO, FixtureSource(), FakeEmbedder(), store)
    monkeypatch.setattr(chunking, "CHUNKER_VERSION", chunking.CHUNKER_VERSION + 1)

    result = ingest(REPO, FixtureSource(), FakeEmbedder(), store)

    assert result.created
    assert len(store.chunks(result.snapshot)) == result.chunk_count


def test_a_snapshot_from_before_index_versions_is_ingested_again(store: ChunkStore) -> None:
    ingest(REPO, FixtureSource(), FakeEmbedder(), store)
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        conn.execute("ALTER TABLE snapshots DROP COLUMN index_version")
    store.setup()

    result = ingest(REPO, FixtureSource(), FakeEmbedder(), store)

    assert result.created


class RacingSource(FixtureSource):
    """Another ingest of the same Snapshot finishes while this one downloads."""

    def __init__(self, store: ChunkStore) -> None:
        super().__init__()
        self.store = store

    def download(self, snapshot: Snapshot, dest: Path) -> None:
        ingest(REPO, FixtureSource(), FakeEmbedder(), self.store)
        super().download(snapshot, dest)


def test_ingesting_a_snapshot_twice_at_once_fails_cleanly(store: ChunkStore) -> None:
    with pytest.raises(IngestError, match=f"acme/shop@{SHA} is being ingested elsewhere"):
        ingest(REPO, RacingSource(store), FakeEmbedder(), store)

    assert store.find(Snapshot("acme", "shop", SHA)) is not None


def test_embedded_text_names_the_file_and_symbol(store: ChunkStore) -> None:
    embedder = FakeEmbedder()

    ingest(REPO, FixtureSource(), embedder, store)

    assert "web/src/api.ts\nfetchSession\n\nexport async function fetchSession()" in "\n".join(
        embedder.texts
    )


def test_repo_over_the_file_limit_is_rejected(store: ChunkStore, tmp_path: Path) -> None:
    for i in range(2001):
        (tmp_path / f"mod_{i}.py").write_text(f"X = {i}\n")

    with pytest.raises(IngestError, match="2001 source files"):
        ingest(REPO, FixtureSource(tmp_path), FakeEmbedder(), store)

    assert store.chunks(Snapshot("acme", "shop", SHA)) == []
