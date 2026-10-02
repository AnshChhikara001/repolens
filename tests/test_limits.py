import pytest
from pydantic import SecretStr

from repolens.config import ModelConfigError, Settings
from repolens.limits import DemoLimits, LimitExceeded, llm_for_visitor
from repolens.llm import GeminiLLM

pytestmark = pytest.mark.usefixtures("clean_env")

HOUR = 3600.0
DAY = 24 * HOUR


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def demo(per_hour: int = 2, per_day: int = 100) -> tuple[Settings, DemoLimits, Clock]:
    settings = Settings(
        google_api_key=SecretStr("our-key"),
        demo_runs_per_hour=per_hour,
        demo_runs_per_day=per_day,
    )
    clock = Clock()
    return settings, DemoLimits(settings, clock), clock


def test_runs_on_our_key_until_one_address_hits_its_hourly_limit() -> None:
    settings, limits, _ = demo(per_hour=2)

    assert isinstance(llm_for_visitor(settings, limits, "1.1.1.1", None), GeminiLLM)
    llm_for_visitor(settings, limits, "1.1.1.1", None)

    with pytest.raises(LimitExceeded, match="2 questions an hour") as exc:
        llm_for_visitor(settings, limits, "1.1.1.1", None)
    assert exc.value.retry_after_s == HOUR


def test_the_hourly_limit_is_per_address() -> None:
    settings, limits, _ = demo(per_hour=1)
    llm_for_visitor(settings, limits, "1.1.1.1", None)

    llm_for_visitor(settings, limits, "2.2.2.2", None)


def test_an_address_gets_runs_back_as_its_oldest_leave_the_hour() -> None:
    settings, limits, clock = demo(per_hour=2)
    llm_for_visitor(settings, limits, "1.1.1.1", None)
    clock.now += 600
    llm_for_visitor(settings, limits, "1.1.1.1", None)

    clock.now += HOUR - 600 - 1
    with pytest.raises(LimitExceeded) as exc:
        llm_for_visitor(settings, limits, "1.1.1.1", None)
    assert exc.value.retry_after_s == 1

    clock.now += 1
    llm_for_visitor(settings, limits, "1.1.1.1", None)


def test_all_addresses_share_a_daily_cap() -> None:
    settings, limits, clock = demo(per_day=3)
    for address in ["1.1.1.1", "2.2.2.2", "3.3.3.3"]:
        llm_for_visitor(settings, limits, address, None)
        clock.now += HOUR

    with pytest.raises(LimitExceeded, match="daily limit of 3 questions") as exc:
        llm_for_visitor(settings, limits, "4.4.4.4", None)
    assert exc.value.retry_after_s == DAY - 3 * HOUR

    clock.now += exc.value.retry_after_s
    llm_for_visitor(settings, limits, "4.4.4.4", None)


def test_a_refused_run_does_not_use_up_the_daily_cap() -> None:
    settings, limits, _ = demo(per_hour=1, per_day=2)
    llm_for_visitor(settings, limits, "1.1.1.1", None)
    for _ in range(5):
        with pytest.raises(LimitExceeded):
            llm_for_visitor(settings, limits, "1.1.1.1", None)

    llm_for_visitor(settings, limits, "2.2.2.2", None)


def test_the_message_offers_the_visitors_own_key() -> None:
    settings, limits, _ = demo(per_hour=0)

    with pytest.raises(LimitExceeded, match="or use your own API key"):
        llm_for_visitor(settings, limits, "1.1.1.1", None)


def test_a_visitors_own_key_bypasses_both_limits_and_uses_none_of_them() -> None:
    settings, limits, _ = demo(per_hour=1, per_day=1)

    for _ in range(3):
        llm_for_visitor(settings, limits, "1.1.1.1", "their-key")

    llm_for_visitor(settings, limits, "1.1.1.1", None)


def test_a_visitors_own_key_is_the_one_the_model_uses() -> None:
    settings = Settings()  # no key of ours
    limits = DemoLimits(settings, Clock())

    model = llm_for_visitor(settings, limits, "1.1.1.1", "their-key")

    assert isinstance(model, GeminiLLM)
    with pytest.raises(ModelConfigError, match="GOOGLE_API_KEY is not set"):
        llm_for_visitor(settings, limits, "1.1.1.1", None)


def test_a_blank_key_is_not_a_key() -> None:
    settings, limits, _ = demo(per_hour=0)

    with pytest.raises(LimitExceeded):
        llm_for_visitor(settings, limits, "1.1.1.1", "  ")


def test_a_visitors_key_cannot_go_to_a_local_models_provider() -> None:
    settings = Settings(chat_model="fake:scripted")
    limits = DemoLimits(settings, Clock())

    with pytest.raises(ModelConfigError, match="own API key works only with"):
        llm_for_visitor(settings, limits, "1.1.1.1", "their-key")
