"""Cross-encoder reranking of retrieved Chunks (ADR-0005)."""

from collections.abc import Sequence
from typing import Protocol

from fastembed.rerank.cross_encoder import TextCrossEncoder

from repolens.chunking import Chunk

# 22M parameters, ONNX on CPU. Reads at most 512 tokens of each question and Chunk.
RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"


class Reranker(Protocol):
    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        """Return how well each text answers the query, higher is better."""
        ...


class CrossEncoderReranker:
    """Scores with a local cross-encoder. The model is downloaded on first use."""

    def __init__(self) -> None:
        self._model = TextCrossEncoder(RERANK_MODEL)

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        return list(self._model.rerank(query, texts))


def rerank(question: str, chunks: Sequence[Chunk], reranker: Reranker, limit: int) -> list[Chunk]:
    """Keep the `limit` Chunks the reranker scores highest, best first."""
    if not chunks:
        return []
    texts = [f"{chunk.path} {chunk.symbol}\n{chunk.text}" for chunk in chunks]
    scores = reranker.score(question, texts)
    ranked = sorted(range(len(chunks)), key=lambda i: -scores[i])  # stable: ties keep search order
    return [chunks[i] for i in ranked[:limit]]
