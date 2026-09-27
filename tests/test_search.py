from repolens.chunking import Chunk
from repolens.embedding import EMBEDDING_DIMENSIONS
from repolens.snapshot import Snapshot
from repolens.store import ChunkStore

SNAPSHOT = Snapshot("acme", "shop", "a" * 40)


def axis(i: int) -> list[float]:
    """A unit vector: chunks on the same axis as the question are the most similar."""
    vector = [0.0] * EMBEDDING_DIMENSIONS
    vector[i] = 1.0
    return vector


HASHING = Chunk("app/auth.py", 6, 7, "hash_password", "return sha256(SALT + password)")
SESSION = Chunk("web/src/api.ts", 5, 8, "fetchSession", 'await fetch("/api/session")')
ASSETS = Chunk("app/build/steps.py", 1, 2, "compile_assets", "pass")


def save(store: ChunkStore, snapshot: Snapshot, chunks: dict[Chunk, list[float]]) -> None:
    store.save(snapshot, len({c.path for c in chunks}), list(chunks), list(chunks.values()), "m")


def test_search_fuses_keyword_and_semantic_matches(store: ChunkStore) -> None:
    save(store, SNAPSHOT, {HASHING: axis(0), SESSION: axis(1), ASSETS: axis(2)})

    # Only HASHING mentions passwords; only SESSION is close to the question's embedding.
    results = store.search(SNAPSHOT, "Where are passwords hashed?", axis(1), limit=3)

    assert set(results[:2]) == {HASHING, SESSION}
    assert results[2] == ASSETS


def test_search_matches_path_segments(store: ChunkStore) -> None:
    save(store, SNAPSHOT, {HASHING: axis(1), SESSION: axis(2), ASSETS: axis(3)})

    results = store.search(SNAPSHOT, "What's in the build folder and the session API?", axis(0), 2)

    assert set(results) == {ASSETS, SESSION}


def test_search_without_keywords_falls_back_to_embeddings(store: ChunkStore) -> None:
    save(store, SNAPSHOT, {HASHING: axis(0), SESSION: axis(1)})

    results = store.search(SNAPSHOT, "how does it do that?", axis(1), limit=1)

    assert results == [SESSION]


def test_search_only_looks_in_the_given_snapshot(store: ChunkStore) -> None:
    other = Snapshot("acme", "shop", "b" * 40)
    save(store, SNAPSHOT, {HASHING: axis(0)})
    save(store, other, {SESSION: axis(0)})

    assert store.search(other, "password session", axis(0), limit=5) == [SESSION]
