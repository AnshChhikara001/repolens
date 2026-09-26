import json

import httpx2

from repolens.embedding import OpenAIEmbedder


class FakeOpenAI:
    """Answers embedding requests with [input length, request number], in reverse order."""

    def __init__(self) -> None:
        self.requests: list[list[str]] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        inputs: list[str] = json.loads(request.content)["input"]
        self.requests.append(inputs)
        data = [
            {"object": "embedding", "index": i, "embedding": [len(text), len(self.requests)]}
            for i, text in reversed(list(enumerate(inputs)))
        ]
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "data": data,
                "model": "text-embedding-3-small",
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )


def embedder(api: FakeOpenAI) -> OpenAIEmbedder:
    return OpenAIEmbedder("sk-test", http_client=httpx2.Client(transport=httpx2.MockTransport(api)))


def test_large_inputs_are_sent_in_batches_and_returned_in_order() -> None:
    api = FakeOpenAI()
    texts = [f"{i:02d}" + "x" * 7_000 for i in range(40)]

    vectors = embedder(api).embed(texts)

    assert [len(batch) for batch in api.requests] == [35, 5]
    assert vectors[0] == [7002, 1]
    assert vectors[34] == [7002, 1]
    assert vectors[35] == [7002, 2]
    assert [batch[0][:2] for batch in api.requests] == ["00", "35"]


def test_overlong_input_is_truncated() -> None:
    api = FakeOpenAI()

    vectors = embedder(api).embed(["y" * 20_000])

    assert vectors == [[8_000, 1]]


def test_truncation_counts_bytes_not_characters() -> None:
    api = FakeOpenAI()

    vectors = embedder(api).embed(["é" * 8_000])

    assert vectors == [[4_000, 1]]


def test_no_texts_means_no_requests() -> None:
    api = FakeOpenAI()

    assert embedder(api).embed([]) == []
    assert api.requests == []
