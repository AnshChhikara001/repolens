"""Limits that keep a public demo from draining our API keys.

Runs on our key are capped per visitor address per hour and for everyone together per day (a
rolling 24 hours). A visitor who brings their own key skips both and uses up neither. Counts
live in memory: the demo is one process, and a restart only resets them.
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from repolens.config import Settings
from repolens.llm import LLM
from repolens.models import build_llm

HOUR = 3600.0
DAY = 24 * HOUR


class LimitExceeded(Exception):
    """A Run on our key would go over a demo limit."""

    def __init__(self, message: str, retry_after_s: float) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class DemoLimits:
    """Counts the Runs started on our key, by visitor address."""

    def __init__(self, settings: Settings, clock: Callable[[], float] = time.time) -> None:
        self.per_hour = settings.demo_runs_per_hour
        self.per_day = settings.demo_runs_per_day
        self._clock = clock
        self._runs: deque[tuple[float, str]] = deque()  # (started, address), oldest first
        self._lock = threading.Lock()

    def admit(self, address: str) -> None:
        """Count a Run from `address`, or raise `LimitExceeded` without counting it."""
        with self._lock:
            now = self._clock()
            while self._runs and now - self._runs[0][0] >= DAY:
                self._runs.popleft()
            today = [started for started, _ in self._runs]
            if len(today) >= self.per_day:
                wait = _wait(today, self.per_day, DAY, now)
                raise LimitExceeded(
                    f"The demo's daily limit of {self.per_day} questions is used up."
                    f" Try again in {_say(wait)}, or use your own API key.",
                    wait,
                )
            hour = [s for s, a in self._runs if a == address and now - s < HOUR]
            if len(hour) >= self.per_hour:
                wait = _wait(hour, self.per_hour, HOUR, now)
                raise LimitExceeded(
                    f"The demo allows {self.per_hour} questions an hour from one address."
                    f" Try again in {_say(wait)}, or use your own API key.",
                    wait,
                )
            self._runs.append((now, address))


def llm_for_visitor(
    settings: Settings, limits: DemoLimits, address: str, api_key: str | None
) -> LLM:
    """The chat model for a visitor's Run: on their key if they gave one, else on ours."""
    if api_key and api_key.strip():
        return build_llm(settings, api_key=api_key.strip())
    llm = build_llm(settings)
    limits.admit(address)
    return llm


def _wait(started: list[float], limit: int, window: float, now: float) -> float:
    """Seconds until one of the `started` Runs leaves the window and frees a place."""
    if limit <= 0:
        return window
    return started[-limit] + window - now


def _say(seconds: float) -> str:
    if seconds > HOUR:
        return f"{math.ceil(seconds / HOUR)} h"
    return f"{max(1, math.ceil(seconds / 60))} min"
