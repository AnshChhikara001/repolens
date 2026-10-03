import pytest

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
TEST_HASHING = Chunk(
    "tests/test_auth.py", 1, 2, "test_hash_password", "assert hash_password('pw') != 'pw'"
)


def save(store: ChunkStore, snapshot: Snapshot, chunks: dict[Chunk, list[float]]) -> None:
    store.save(
        snapshot, len({c.path for c in chunks}), list(chunks), list(chunks.values()), "m", "v"
    )


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


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_auth.py",
        "test/auth.ts",
        "app/test_auth.py",
        "app/conftest.py",
        "web/src/__tests__/auth.js",
        "web/src/auth.test.ts",
        "web/src/auth.spec.ts",
        "pkg/auth/auth_test.go",
    ],
)
def test_search_ranks_tests_below_source(store: ChunkStore, path: str) -> None:
    test = Chunk(path, 1, 2, "<module>", "assert hash_password('pw') != 'pw'")
    save(store, SNAPSHOT, {test: axis(0), HASHING: axis(1), SESSION: axis(2)})

    # The test matches the question best, by keywords and by meaning.
    results = store.search(SNAPSHOT, "How is hash_password checked?", axis(0), limit=3)

    assert results == [HASHING, SESSION, test]


@pytest.mark.parametrize("path", ["app/testing.py", "app/latest.py", "app/inspect.py"])
def test_search_ranks_source_named_like_tests_as_source(store: ChunkStore, path: str) -> None:
    helper = Chunk(path, 1, 2, "<module>", "assert hash_password('pw') != 'pw'")
    save(store, SNAPSHOT, {helper: axis(0), HASHING: axis(1), SESSION: axis(2)})

    results = store.search(SNAPSHOT, "How is hash_password checked?", axis(0), limit=3)

    assert results[0] == helper


@pytest.mark.parametrize(
    "query",
    ["test_hash_password", "How is hashing tested?", "the tests for hash_password", "Test hashing"],
)
def test_a_search_that_mentions_tests_ranks_them_like_source(store: ChunkStore, query: str) -> None:
    save(store, SNAPSHOT, {TEST_HASHING: axis(0), HASHING: axis(1), SESSION: axis(2)})

    assert store.search(SNAPSHOT, query, axis(0), limit=1) == [TEST_HASHING]


@pytest.mark.parametrize("query", ["the latest hash", "a specific hash", "TestClient hashing"])
def test_words_containing_test_or_spec_dont_count_as_mentioning_tests(
    store: ChunkStore, query: str
) -> None:
    save(store, SNAPSHOT, {TEST_HASHING: axis(0), HASHING: axis(1)})

    assert store.search(SNAPSHOT, query, axis(0), limit=1) == [HASHING]
