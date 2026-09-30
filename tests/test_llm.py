"""The chat model adapters, against recorded provider responses (no network)."""

import json
import logging
from collections.abc import Callable
from typing import Any

import anthropic
import httpx
import httpx2
import pytest
from pydantic import BaseModel

from repolens.llm import AnthropicLLM, GeminiLLM, LLMError


class Answer(BaseModel):
    text: str
    confidence: int


SYSTEM = "Answer briefly."
QUESTION = "What is 2 + 2?"
ANSWER = Answer(text="Four", confidence=9)


class Recorder:
    """Records each request and answers it with a canned response or error."""

    def __init__(self, respond: Callable[[Any], Any]) -> None:
        self.respond = respond
        self.bodies: list[dict[str, Any]] = []
        self.urls: list[str] = []
        self.waits: list[float] = []

    def __call__(self, request: Any) -> Any:
        self.urls.append(str(request.url))
        self.bodies.append(json.loads(request.content))
        return self.respond(request)


def gemini(
    respond: Callable[[httpx.Request], httpx.Response], max_retries: int = 0
) -> tuple[GeminiLLM, Recorder]:
    recorder = Recorder(respond)
    client = httpx.Client(transport=httpx.MockTransport(recorder))
    llm = GeminiLLM(
        "gemini-test",
        api_key="g-key",
        timeout=30,
        http_client=client,
        max_retries=max_retries,
        sleep=recorder.waits.append,
    )
    return llm, recorder


def gemini_reply(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [{"content": {"role": "model", "parts": [{"text": text}]}}],
            "usageMetadata": {
                "promptTokenCount": 12,
                "candidatesTokenCount": 5,
                "thoughtsTokenCount": 3,
            },
        },
    )


def test_gemini_returns_the_parsed_answer_and_its_usage() -> None:
    llm, recorder = gemini(lambda request: gemini_reply(ANSWER.model_dump_json()))

    reply = llm.structured(SYSTEM, QUESTION, Answer)

    assert llm.name == "google:gemini-test"
    assert reply.value == ANSWER
    assert (reply.input_tokens, reply.output_tokens) == (12, 5 + 3)  # thinking is output
    assert reply.latency_s >= 0
    [body] = recorder.bodies
    assert "models/gemini-test:generateContent" in recorder.urls[0]
    assert body["systemInstruction"]["parts"] == [{"text": SYSTEM}]
    assert body["contents"][0]["parts"] == [{"text": QUESTION}]
    assert body["generationConfig"]["temperature"] == 0
    assert body["generationConfig"]["responseJsonSchema"]["required"] == ["text", "confidence"]


def test_gemini_calls_log_no_warnings(caplog: pytest.LogCaptureFixture) -> None:
    llm, _ = gemini(lambda request: gemini_reply(ANSWER.model_dump_json()))

    llm.structured(SYSTEM, QUESTION, Answer)

    assert [record.message for record in caplog.records if record.levelno >= logging.WARNING] == []


def test_gemini_provider_errors_are_one_readable_line() -> None:
    overloaded = {
        "error": {"code": 503, "message": "The model is overloaded.", "status": "UNAVAILABLE"}
    }
    llm, _ = gemini(lambda request: httpx.Response(503, json=overloaded))

    with pytest.raises(LLMError) as error:
        llm.structured(SYSTEM, QUESTION, Answer)

    assert str(error.value) == "google:gemini-test: 503 UNAVAILABLE, The model is overloaded."


def rate_limited(retry_delay: str | None) -> httpx.Response:
    details: list[dict[str, str]] = [{"@type": "type.googleapis.com/google.rpc.QuotaFailure"}]
    if retry_delay is not None:
        retry_info = {"@type": "type.googleapis.com/google.rpc.RetryInfo"}
        details.append(retry_info | {"retryDelay": retry_delay})
    error = {"code": 429, "message": "Quota exceeded.", "status": "RESOURCE_EXHAUSTED"}
    return httpx.Response(429, json={"error": error | {"details": details}})


def test_a_gemini_rate_limit_is_retried_once_after_the_delay_it_asks_for() -> None:
    replies = iter([rate_limited("7s"), gemini_reply(ANSWER.model_dump_json())])
    llm, recorder = gemini(lambda request: next(replies))

    reply = llm.structured(SYSTEM, QUESTION, Answer)

    assert reply.value == ANSWER
    assert recorder.waits == [7.0]
    assert len(recorder.bodies) == 2


def test_a_gemini_rate_limit_after_the_retry_is_an_error() -> None:
    llm, recorder = gemini(lambda request: rate_limited("0.5s"))

    with pytest.raises(LLMError, match=r"^google:gemini-test: 429 RESOURCE_EXHAUSTED, Quota"):
        llm.structured(SYSTEM, QUESTION, Answer)

    assert recorder.waits == [0.5]
    assert len(recorder.bodies) == 2


@pytest.mark.parametrize("retry_delay", [None, "3600s"])
def test_a_gemini_rate_limit_without_a_short_delay_is_not_retried(retry_delay: str | None) -> None:
    llm, recorder = gemini(lambda request: rate_limited(retry_delay))

    with pytest.raises(LLMError, match="429 RESOURCE_EXHAUSTED"):
        llm.structured(SYSTEM, QUESTION, Answer)

    assert recorder.waits == []
    assert len(recorder.bodies) == 1


def test_gemini_rate_limits_are_left_to_our_retry_not_the_sdk_backoff() -> None:
    replies = iter([rate_limited("7s"), gemini_reply(ANSWER.model_dump_json())])
    llm, recorder = gemini(lambda request: next(replies), max_retries=2)

    llm.structured(SYSTEM, QUESTION, Answer)

    assert recorder.waits == [7.0]


def test_gemini_timeouts_are_timeout_errors() -> None:
    def time_out(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    llm, _ = gemini(time_out)

    with pytest.raises(TimeoutError):
        llm.structured(SYSTEM, QUESTION, Answer)


def test_gemini_network_errors_are_one_readable_line() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    llm, _ = gemini(refuse)

    with pytest.raises(LLMError, match=r"^google:gemini-test: connection refused$"):
        llm.structured(SYSTEM, QUESTION, Answer)


def test_a_gemini_answer_that_does_not_fit_the_schema_is_an_error() -> None:
    llm, _ = gemini(lambda request: gemini_reply('{"text": "Four"}'))

    with pytest.raises(LLMError, match=r"google:gemini-test: the answer doesn't fit Answer"):
        llm.structured(SYSTEM, QUESTION, Answer)


def claude(respond: Callable[[httpx2.Request], httpx2.Response]) -> tuple[AnthropicLLM, Recorder]:
    recorder = Recorder(respond)
    client = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(recorder))
    llm = AnthropicLLM(
        "claude-test", api_key="a-key", timeout=30, http_client=client, max_retries=0
    )
    return llm, recorder


def claude_reply(text: str, stop_reason: str = "end_turn") -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-test",
            "content": [{"type": "text", "text": text}],
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 12, "output_tokens": 5},
        },
    )


def test_claude_returns_the_parsed_answer_and_its_usage() -> None:
    llm, recorder = claude(lambda request: claude_reply(ANSWER.model_dump_json()))

    reply = llm.structured(SYSTEM, QUESTION, Answer)

    assert llm.name == "anthropic:claude-test"
    assert reply.value == ANSWER
    assert (reply.input_tokens, reply.output_tokens) == (12, 5)
    assert reply.latency_s >= 0
    [body] = recorder.bodies
    assert body["model"] == "claude-test"
    assert body["system"] == SYSTEM
    assert body["messages"] == [{"role": "user", "content": QUESTION}]
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["schema"]["required"] == ["text", "confidence"]


def test_claude_provider_errors_are_one_readable_line() -> None:
    overloaded = {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}
    llm, _ = claude(lambda request: httpx2.Response(529, json=overloaded))

    with pytest.raises(LLMError) as error:
        llm.structured(SYSTEM, QUESTION, Answer)

    assert str(error.value) == "anthropic:claude-test: 529 overloaded_error, Overloaded"


def test_claude_timeouts_are_timeout_errors() -> None:
    def time_out(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out", request=request)

    llm, _ = claude(time_out)

    with pytest.raises(TimeoutError):
        llm.structured(SYSTEM, QUESTION, Answer)


@pytest.mark.parametrize(
    "response",
    [claude_reply('{"text": "Four"}'), claude_reply('{"text": "Fo', stop_reason="max_tokens")],
    ids=["wrong shape", "cut off"],
)
def test_a_claude_answer_that_does_not_fit_the_schema_is_an_error(
    response: httpx2.Response,
) -> None:
    llm, _ = claude(lambda request: response)

    with pytest.raises(LLMError, match=r"anthropic:claude-test: the answer doesn't fit Answer"):
        llm.structured(SYSTEM, QUESTION, Answer)
