from collections.abc import Iterator, Sequence
from typing import Protocol

import httpx2
from openai import OpenAI

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# The API takes at most 8,191 tokens per input and 300k tokens per request.
# In practice a token is at least one character, so counting characters is safe.
MAX_INPUT_CHARS = 8_000
MAX_BATCH_CHARS = 250_000
MAX_BATCH_INPUTS = 2_048


class Embedder(Protocol):
    model: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one EMBEDDING_DIMENSIONS-long vector per text, in order."""
        ...


class OpenAIEmbedder:
    model = EMBEDDING_MODEL

    def __init__(self, api_key: str, http_client: httpx2.Client | None = None) -> None:
        self._client = OpenAI(api_key=api_key, http_client=http_client)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for batch in _batches([text[:MAX_INPUT_CHARS] for text in texts]):
            response = self._client.embeddings.create(
                input=batch, model=self.model, encoding_format="float"
            )
            vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
        return vectors


def _batches(texts: list[str]) -> Iterator[list[str]]:
    batch: list[str] = []
    size = 0
    for text in texts:
        if batch and (size + len(text) > MAX_BATCH_CHARS or len(batch) == MAX_BATCH_INPUTS):
            yield batch
            batch, size = [], 0
        batch.append(text)
        size += len(text)
    if batch:
        yield batch
