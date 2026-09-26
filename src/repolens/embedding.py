from collections.abc import Iterator, Sequence
from typing import Protocol

import httpx2
from openai import OpenAI

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# The API takes at most 8,191 tokens per input and 300k tokens per request.
# A token covers at least one UTF-8 byte, so limits in bytes are safe.
MAX_INPUT_BYTES = 8_000
MAX_BATCH_BYTES = 250_000
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
        for batch in _batches([_truncate(text) for text in texts]):
            response = self._client.embeddings.create(
                input=batch, model=self.model, encoding_format="float"
            )
            vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
        return vectors


def _truncate(text: str) -> str:
    return text.encode()[:MAX_INPUT_BYTES].decode(errors="ignore")


def _batches(texts: list[str]) -> Iterator[list[str]]:
    batch: list[str] = []
    size = 0
    for text in texts:
        length = len(text.encode())
        if batch and (size + length > MAX_BATCH_BYTES or len(batch) == MAX_BATCH_INPUTS):
            yield batch
            batch, size = [], 0
        batch.append(text)
        size += length
    if batch:
        yield batch
