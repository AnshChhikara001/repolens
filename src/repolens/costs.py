"""Prices for model calls, and a callback that records what each call cost (ADR-0004)."""

from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from typing import Any
from uuid import UUID

import yaml
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from pydantic import BaseModel, TypeAdapter

from repolens.config import ModelConfigError

PRICES_FILE = "prices.yaml"


class Price(BaseModel):
    """USD per million tokens at the paid tier."""

    input: float
    output: float
    free_tier: bool = False


@dataclass(frozen=True)
class ModelCall:
    """One chat model call and what it cost. Free-tier calls cost their Shadow cost."""

    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    shadow: bool


class PriceTable:
    """Prices by `provider:model`, the same form as CHAT_MODEL."""

    def __init__(self, prices: Mapping[str, Price]) -> None:
        self._prices = dict(prices)

    def require(self, model: str) -> Price:
        """The model's price, or a ModelConfigError: every call must be priced."""
        price = self._prices.get(model)
        if price is None:
            raise ModelConfigError(f"no price for {model} in {PRICES_FILE} or LOCAL_MODELS")
        return price

    def merged(self, prices: Mapping[str, Price]) -> "PriceTable":
        """This table plus prices for models it doesn't price. Reviewed prices can't change."""
        if repriced := sorted(prices.keys() & self._prices.keys()):
            raise ModelConfigError(f"{', '.join(repriced)} is priced in {PRICES_FILE} already")
        return PriceTable({**self._prices, **prices})

    def call(self, model: str, input_tokens: int, output_tokens: int) -> ModelCall:
        """Price one call."""
        price = self.require(model)
        cost = (input_tokens * price.input + output_tokens * price.output) / 1_000_000
        return ModelCall(model, input_tokens, output_tokens, cost, shadow=price.free_tier)


def load_prices(text: str | None = None) -> PriceTable:
    """Read a price table, by default the reviewed one shipped with repolens."""
    if text is None:
        text = files("repolens").joinpath(PRICES_FILE).read_text()
    models = TypeAdapter(dict[str, Price]).validate_python(yaml.safe_load(text)["models"])
    return PriceTable(models)


class CostTracker(BaseCallbackHandler):
    """Prices every chat model call made under it from the token usage it reports.

    An unpriced model fails before it is called. A call that reports no token usage is
    recorded at zero tokens, so every call has a row.
    """

    raise_error = True

    def __init__(self, prices: PriceTable) -> None:
        self.prices = prices
        self.calls: list[ModelCall] = []
        # LangChain's `run_id` here identifies one model call, not a Run.
        self._model_by_call: dict[UUID, str] = {}

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        metadata = metadata or {}
        model = f"{metadata.get('ls_provider')}:{metadata.get('ls_model_name')}"
        self.prices.require(model)
        self._model_by_call[run_id] = model

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        model = self._model_by_call.pop(run_id)
        input_tokens = output_tokens = 0
        for generation in (g for gs in response.generations for g in gs):
            message = generation.message if isinstance(generation, ChatGeneration) else None
            if not isinstance(message, AIMessage) or message.usage_metadata is None:
                continue
            input_tokens += message.usage_metadata["input_tokens"]
            output_tokens += message.usage_metadata["output_tokens"]
        self.calls.append(self.prices.call(model, input_tokens, output_tokens))

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._model_by_call.pop(run_id, None)
