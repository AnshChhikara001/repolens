import pytest

from repolens.config import DEFAULT_CHAT_MODEL, ModelConfigError
from repolens.costs import ModelCall, Price, PriceTable, load_prices

PRICES = PriceTable(
    {
        "google_genai:free": Price(input=0.5, output=3.0, free_tier=True),
        "openai:paid": Price(input=0.1, output=0.4),
    }
)


def test_calls_are_priced_per_million_tokens() -> None:
    call = PRICES.call("openai:paid", input_tokens=2_000_000, output_tokens=500_000)

    assert call == ModelCall("openai:paid", 2_000_000, 500_000, 0.4, shadow=False)


def test_free_tier_calls_are_charged_at_shadow_cost() -> None:
    call = PRICES.call("google_genai:free", input_tokens=1_000_000, output_tokens=1_000_000)

    assert call.cost_usd == pytest.approx(3.5)
    assert call.shadow


def test_an_unpriced_model_is_an_error() -> None:
    with pytest.raises(ModelConfigError, match=r"groq:llama in prices\.yaml"):
        PRICES.call("groq:llama", input_tokens=1, output_tokens=1)


def test_prices_are_read_from_yaml() -> None:
    prices = load_prices("models:\n  openai:paid: {input: 0.1, output: 0.4}\n")

    assert prices.require("openai:paid") == Price(input=0.1, output=0.4)
    assert prices.call("openai:paid", 1_000_000, 0).cost_usd == pytest.approx(0.1)


def test_the_bundled_table_prices_the_default_chat_model_at_shadow_cost() -> None:
    assert load_prices().call(DEFAULT_CHAT_MODEL, 1, 1).shadow
