from rag.answer import OFFLINE_MESSAGE
from rag.circuit_breaker import CLOSED, HALF_OPEN, OPEN, CircuitBreaker


class _FakeAnswerer:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def answer(self, question, context_block):
        self.calls += 1
        return self._responses.pop(0)


class _FakeClock:
    def __init__(self, start=0.0):
        self._now = start

    def __call__(self):
        return self._now

    def advance(self, seconds):
        self._now += seconds


def test_breaker_starts_closed():
    breaker = CircuitBreaker(_FakeAnswerer(["anything"]))

    assert breaker.state == CLOSED


def test_breaker_opens_after_three_consecutive_failures():
    wrapped = _FakeAnswerer([OFFLINE_MESSAGE, OFFLINE_MESSAGE, OFFLINE_MESSAGE])
    breaker = CircuitBreaker(wrapped, failure_threshold=3)

    breaker.answer("q", "c")
    breaker.answer("q", "c")
    assert breaker.state == CLOSED
    breaker.answer("q", "c")

    assert breaker.state == OPEN


def test_breaker_open_short_circuits_without_calling_the_wrapped_function():
    wrapped = _FakeAnswerer([OFFLINE_MESSAGE, OFFLINE_MESSAGE, OFFLINE_MESSAGE])
    breaker = CircuitBreaker(wrapped, failure_threshold=3)
    for _ in range(3):
        breaker.answer("q", "c")
    assert breaker.state == OPEN

    result = breaker.answer("q", "c")

    assert result == OFFLINE_MESSAGE
    assert wrapped.calls == 3  # the short-circuited call never reached the wrapped function


def test_breaker_a_success_before_the_threshold_resets_the_failure_count():
    wrapped = _FakeAnswerer(
        [OFFLINE_MESSAGE, OFFLINE_MESSAGE, "a real answer", OFFLINE_MESSAGE, OFFLINE_MESSAGE]
    )
    breaker = CircuitBreaker(wrapped, failure_threshold=3)

    breaker.answer("q", "c")
    breaker.answer("q", "c")
    breaker.answer("q", "c")  # success resets the counter
    breaker.answer("q", "c")
    breaker.answer("q", "c")

    assert breaker.state == CLOSED  # only 2 consecutive failures since the reset


def test_breaker_treats_any_non_offline_string_as_success_even_if_it_looks_failure_like():
    wrapped = _FakeAnswerer(["error: something failed", OFFLINE_MESSAGE, OFFLINE_MESSAGE])
    breaker = CircuitBreaker(wrapped, failure_threshold=2)

    breaker.answer("q", "c")  # looks like a failure string, but isn't OFFLINE_MESSAGE -- success
    breaker.answer("q", "c")
    breaker.answer("q", "c")

    assert breaker.state == OPEN  # opened by the 2 real OFFLINE_MESSAGE failures, not 3


def test_breaker_transitions_to_half_open_after_the_cooldown_elapses():
    clock = _FakeClock()
    wrapped = _FakeAnswerer([OFFLINE_MESSAGE, OFFLINE_MESSAGE, OFFLINE_MESSAGE])
    breaker = CircuitBreaker(wrapped, failure_threshold=3, cooldown_seconds=60.0, time_func=clock)
    for _ in range(3):
        breaker.answer("q", "c")
    assert breaker.state == OPEN

    clock.advance(59.0)
    assert breaker.state == OPEN

    clock.advance(1.0)
    assert breaker.state == HALF_OPEN


def test_breaker_half_open_success_closes_the_breaker():
    clock = _FakeClock()
    wrapped = _FakeAnswerer([OFFLINE_MESSAGE, OFFLINE_MESSAGE, OFFLINE_MESSAGE, "back online"])
    breaker = CircuitBreaker(wrapped, failure_threshold=3, cooldown_seconds=60.0, time_func=clock)
    for _ in range(3):
        breaker.answer("q", "c")
    clock.advance(60.0)
    assert breaker.state == HALF_OPEN

    result = breaker.answer("q", "c")

    assert result == "back online"
    assert breaker.state == CLOSED
    assert wrapped.calls == 4  # the half-open probe actually called through to the wrapped function


def test_breaker_half_open_failure_reopens_the_breaker_for_another_cooldown():
    clock = _FakeClock()
    wrapped = _FakeAnswerer([OFFLINE_MESSAGE, OFFLINE_MESSAGE, OFFLINE_MESSAGE, OFFLINE_MESSAGE])
    breaker = CircuitBreaker(wrapped, failure_threshold=3, cooldown_seconds=60.0, time_func=clock)
    for _ in range(3):
        breaker.answer("q", "c")
    clock.advance(60.0)
    assert breaker.state == HALF_OPEN

    result = breaker.answer("q", "c")

    assert result == OFFLINE_MESSAGE
    assert breaker.state == OPEN  # reopened, not stuck at half-open
    assert wrapped.calls == 4  # the probe call did go through

    # The new cooldown restarts from this reopen, not the original one.
    clock.advance(59.0)
    assert breaker.state == OPEN
    clock.advance(1.0)
    assert breaker.state == HALF_OPEN
