"""Chat models behind one small interface: a system prompt and a question in, a typed reply out.

Every adapter asks for JSON that fits a pydantic schema and validates it, so any model that
can return JSON works, without native tool calling. `CHAT_MODEL` names one as `provider:model`.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, cast

import anthropic
import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, Field, ValidationError


@dataclass(frozen=True)
class Reply[T: BaseModel]:
    """A model's answer, what it used and how long it took."""

    value: T
    input_tokens: int
    output_tokens: int
    latency_s: float


class LLM(Protocol):
    """A chat model that answers with JSON fitting a pydantic schema."""

    name: str
    """`provider:model`, as in CHAT_MODEL."""

    def structured[T: BaseModel](self, system: str, user: str, schema: type[T]) -> Reply[T]:
        """Ask for an answer that fits the schema.

        Raises TimeoutError when a request takes longer than CHAT_TIMEOUT, and LLMError when
        the provider fails or the answer doesn't fit.
        """
        ...


class LLMError(Exception):
    """A chat model call failed: a provider error, or an answer that doesn't fit the schema."""


@dataclass(frozen=True)
class ModelCall:
    """One chat model call of a Run: which model, for which schema, and what it used."""

    model: str
    schema: str
    input_tokens: int
    output_tokens: int
    latency_s: float


# Each retry may wait the full CHAT_TIMEOUT, so keep them few.
MAX_RETRIES = 2
# A Gemini rate limit (429) says how long to wait; we wait that long and retry once, unless
# it's longer than this (a daily quota asks for hours).
MAX_RATE_LIMIT_WAIT_S = 60.0
# The SDK's own backoff waits seconds, too short for a quota, so it retries only these.
GEMINI_RETRY_STATUS_CODES = [408, 500, 502, 503, 504]
# Low effort keeps Claude's latency and output tokens down; the answers are short and grounded.
ANTHROPIC_EFFORT = "low"
ANTHROPIC_MAX_TOKENS = 16_000


class GeminiLLM:
    """Gemini through the google-genai SDK, with JSON output constrained to the schema."""

    def __init__(
        self,
        model: str,
        api_key: str,
        timeout: float,
        http_client: httpx.Client | None = None,
        max_retries: int = MAX_RETRIES,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.name = f"google:{model}"
        self._model = model
        self._sleep = sleep
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(timeout * 1000),
                retry_options=types.HttpRetryOptions(
                    attempts=max_retries + 1, http_status_codes=GEMINI_RETRY_STATUS_CODES
                ),
                httpx_client=http_client,
            ),
        )

    def structured[T: BaseModel](self, system: str, user: str, schema: type[T]) -> Reply[T]:
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            response_mime_type="application/json",
            response_json_schema=schema.model_json_schema(),
            # We pass no Python functions as tools, so automatic function calling has no work.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        started = time.perf_counter()
        try:
            try:
                response = self._client.models.generate_content(
                    model=self._model, contents=user, config=config
                )
            except genai_errors.APIError as exc:
                wait_s = _retry_delay(exc)
                if wait_s is None or wait_s > MAX_RATE_LIMIT_WAIT_S:
                    raise
                self._sleep(wait_s)
                started = time.perf_counter()
                response = self._client.models.generate_content(
                    model=self._model, contents=user, config=config
                )
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"{self.name} timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.name}: {exc}") from exc
        except genai_errors.APIError as exc:
            raise LLMError(f"{self.name}: {exc.code} {exc.status}, {exc.message}") from exc
        latency_s = time.perf_counter() - started
        value = _parse(self.name, schema, response.text)
        usage = response.usage_metadata
        input_tokens = (usage and usage.prompt_token_count) or 0
        # Thinking tokens are billed as output.
        output_tokens = ((usage and usage.candidates_token_count) or 0) + (
            (usage and usage.thoughts_token_count) or 0
        )
        return Reply(value, input_tokens, output_tokens, latency_s)


class AnthropicLLM:
    """Claude through the Anthropic API, with structured outputs."""

    def __init__(
        self,
        model: str,
        api_key: str,
        timeout: float,
        http_client: anthropic.DefaultHttpxClient | None = None,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self.name = f"anthropic:{model}"
        self._model = model
        self._client = anthropic.Anthropic(
            api_key=api_key, timeout=timeout, max_retries=max_retries, http_client=http_client
        )

    def structured[T: BaseModel](self, system: str, user: str, schema: type[T]) -> Reply[T]:
        started = time.perf_counter()
        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=ANTHROPIC_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
                output_config={"effort": ANTHROPIC_EFFORT},
            )
        except anthropic.APITimeoutError as exc:
            raise TimeoutError(f"{self.name} timed out") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"{self.name}: {exc.status_code} {_anthropic_error(exc)}") from exc
        except anthropic.APIError as exc:
            raise LLMError(f"{self.name}: {exc.message}") from exc
        except ValidationError as exc:
            raise _misfit(self.name, schema) from exc
        latency_s = time.perf_counter() - started
        if response.parsed_output is None:
            raise _misfit(self.name, schema)
        usage = response.usage
        return Reply(response.parsed_output, usage.input_tokens, usage.output_tokens, latency_s)


class _ErrorDetail(BaseModel):
    retry_delay: str = Field(default="", alias="retryDelay")


class _Error(BaseModel):
    details: list[_ErrorDetail] = []


class _ErrorBody(BaseModel):
    error: _Error


def _retry_delay(exc: genai_errors.APIError) -> float | None:
    """The seconds a Gemini 429 asks us to wait, from its RetryInfo, e.g. `"retryDelay": "7s"`."""
    if exc.code != 429:
        return None
    details = cast(object, exc.details)  # pyright: ignore[reportUnknownMemberType]
    try:
        body = _ErrorBody.model_validate(details)
    except ValidationError:
        return None
    for detail in body.error.details:
        try:
            return float(detail.retry_delay.removesuffix("s"))
        except ValueError:
            continue
    return None


def _parse[T: BaseModel](name: str, schema: type[T], text: str | None) -> T:
    try:
        return schema.model_validate_json(text or "")
    except ValidationError as exc:
        raise _misfit(name, schema) from exc


def _misfit(name: str, schema: type[BaseModel]) -> LLMError:
    return LLMError(f"{name}: the answer doesn't fit {schema.__name__}")


def _anthropic_error(exc: anthropic.APIStatusError) -> str:
    """E.g. `overloaded_error, Overloaded` from the API's error body."""
    body = cast(object, exc.body)
    error = cast(dict[str, object], body).get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        error = cast(dict[str, object], error)
        return f"{error.get('type')}, {error.get('message')}"
    return exc.message
