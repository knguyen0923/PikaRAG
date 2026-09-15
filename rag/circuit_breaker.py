import time
from typing import Callable

from rag.answer import OFFLINE_MESSAGE

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


class CircuitBreaker:
    """Wraps an answerer-like object (anything with .answer(question,
    context_block) -> str) and short-circuits calls after repeated
    failures, so concurrent /ask requests stop each paying a full network
    timeout once the LLM host is known to be down.

    Detects failure by return value, not exception: OllamaAnswerer.answer
    already catches every network/parsing failure internally and returns
    the fixed OFFLINE_MESSAGE string rather than raising, so this breaker
    treats "result == OFFLINE_MESSAGE" as the failure signal.
    """

    def __init__(
        self,
        wrapped,
        failure_threshold: int = 3,
        cooldown_seconds: float = 60.0,
        time_func: Callable[[], float] = time.monotonic,
    ):
        self._wrapped = wrapped
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._time_func = time_func
        self._state = CLOSED
        self._failure_count = 0
        self._opened_at = None

    @property
    def state(self) -> str:
        if self._state == OPEN and self._time_func() - self._opened_at >= self._cooldown_seconds:
            return HALF_OPEN
        return self._state

    def answer(self, question: str, context_block: str) -> str:
        effective_state = self.state
        if effective_state == OPEN:
            return OFFLINE_MESSAGE

        result = self._wrapped.answer(question, context_block)

        if result == OFFLINE_MESSAGE:
            if effective_state == HALF_OPEN:
                self._state = OPEN
                self._opened_at = self._time_func()
            else:
                self._failure_count += 1
                if self._failure_count >= self._failure_threshold:
                    self._state = OPEN
                    self._opened_at = self._time_func()
        else:
            self._state = CLOSED
            self._failure_count = 0

        return result
