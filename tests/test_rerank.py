from fakes import KeywordReranker

from repolens.chunking import Chunk
from repolens.rerank import rerank

HASHING = Chunk("app/auth.py", 6, 7, "hash_password", "return sha256(SALT + password)")
LOGIN = Chunk("app/auth.py", 10, 15, "LoginService", "def login(self, name, password): ...")
SESSION = Chunk("web/src/api.ts", 5, 8, "fetchSession", 'await fetch("/api/session")')


def test_rerank_keeps_the_best_scored_chunks() -> None:
    reranker = KeywordReranker("password", "sha256")

    assert rerank("How are passwords hashed?", [SESSION, LOGIN, HASHING], reranker, 2) == [
        HASHING,
        LOGIN,
    ]


def test_rerank_breaks_ties_by_search_order() -> None:
    chunks = [SESSION, HASHING, LOGIN]

    assert rerank("anything", chunks, KeywordReranker(), 3) == chunks


def test_the_reranker_sees_the_path_and_symbol() -> None:
    reranker = KeywordReranker("fetchSession")

    assert rerank("Where is the session fetched?", [HASHING, SESSION], reranker, 1) == [SESSION]
