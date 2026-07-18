from time import time

from contextlib import contextmanager
from copy import deepcopy
from typing import Iterator

import pytest

from backend.app.resilience.exceptions import CircuitBreakerOpenError
from backend.app.resilience.models import (
    CircuitBreakerPolicy,
    CircuitBreakerSnapshot,
    CircuitState,
)

from backend.app.resilience.service import CircuitBreaker

from backend.app.resilience.metrics import (
    CIRCUIT_BREAKER_REJECTIONS,
    CIRCUIT_BREAKER_STATE,
    CIRCUIT_BREAKER_TRANSITIONS,
    STATE_NUMERIC_VALUE,
)


class InMemoryCircuitBreakerRepository:
    def __init__(self) -> None:
        self._states: dict[str, CircuitBreakerSnapshot] = {}

    @contextmanager
    def lock(
        self,
        name: str,
        timeout_seconds: int,
    ) -> Iterator[None]:
        del name, timeout_seconds
        yield

    def get(self, name: str) -> CircuitBreakerSnapshot:
        snapshot = self._states.get(name)

        if snapshot is None:
            return CircuitBreakerSnapshot.new(name)

        return deepcopy(snapshot)

    def save(
        self,
        snapshot: CircuitBreakerSnapshot,
        ttl_seconds: int,
    ) -> None:
        del ttl_seconds
        self._states[snapshot.name] = deepcopy(snapshot)

    def delete(self, name: str) -> None:
        self._states.pop(name, None)


@pytest.fixture
def policy():
    return CircuitBreakerPolicy(
        failure_threshold=5,
        recovery_timeout_seconds=30,
        half_open_max_calls=1,
        success_threshold=2,
        state_ttl_seconds=3600,
        lock_timeout_seconds=5,
    )


@pytest.fixture
def repository():
    return InMemoryCircuitBreakerRepository()


@pytest.fixture
def breaker(policy, repository):
    return CircuitBreaker(
        name="test.breaker",
        policy=policy,
        repository=repository,
    )


def success():
    return "ok"


def failure():
    raise RuntimeError("boom")


def ignored():
    raise ValueError("ignored")

def test_initial_snapshot_is_closed(breaker):
    snapshot = breaker.get_snapshot()

    assert snapshot.state == CircuitState.CLOSED
    assert snapshot.failure_count == 0
    assert snapshot.success_count == 0


def test_failure_below_threshold_stays_closed(breaker):
    for _ in range(4):
        with pytest.raises(RuntimeError):
            breaker.call(failure)

    snapshot = breaker.get_snapshot()

    assert snapshot.state == CircuitState.CLOSED
    assert snapshot.failure_count == 4
    

def test_closed_transitions_to_open_at_failure_threshold(breaker):
    for _ in range(5):
        with pytest.raises(RuntimeError):
            breaker.call(failure)

    snapshot = breaker.get_snapshot()

    assert snapshot.state == CircuitState.OPEN
    assert snapshot.failure_count == 5
    assert snapshot.opened_at is not None


def test_open_breaker_rejects_request_before_timeout(
    breaker,
    repository,
):
    repository.save(
        CircuitBreakerSnapshot(
            name=breaker.name,
            state=CircuitState.OPEN,
            failure_count=5,
            opened_at=time(),
        ),
        breaker.policy.state_ttl_seconds,
    )

    with pytest.raises(CircuitBreakerOpenError) as exc_info:
        breaker.call(success)

    assert exc_info.value.breaker_name == breaker.name
    assert exc_info.value.retry_after_seconds > 0


def test_open_transitions_to_half_open_after_timeout(
    breaker,
    repository,
):
    repository.save(
        CircuitBreakerSnapshot(
            name=breaker.name,
            state=CircuitState.OPEN,
            failure_count=5,
            opened_at=time() - 31,
        ),
        breaker.policy.state_ttl_seconds,
    )

    result = breaker.call(success)
    snapshot = breaker.get_snapshot()

    assert result == "ok"
    assert snapshot.state == CircuitState.HALF_OPEN
    assert snapshot.success_count == 1
    assert snapshot.half_open_calls == 0


def test_half_open_failure_reopens_breaker(
    breaker,
    repository,
):
    repository.save(
        CircuitBreakerSnapshot(
            name=breaker.name,
            state=CircuitState.HALF_OPEN,
            success_count=1,
            half_open_calls=0,
            opened_at=time() - 31,
        ),
        breaker.policy.state_ttl_seconds,
    )

    with pytest.raises(RuntimeError):
        breaker.call(failure)

    snapshot = breaker.get_snapshot()

    assert snapshot.state == CircuitState.OPEN
    assert snapshot.failure_count == 1
    assert snapshot.success_count == 0
    assert snapshot.half_open_calls == 0
    assert snapshot.opened_at is not None


def test_first_half_open_success_remains_half_open(
    breaker,
    repository,
):
    repository.save(
        CircuitBreakerSnapshot(
            name=breaker.name,
            state=CircuitState.HALF_OPEN,
            success_count=0,
            half_open_calls=0,
            opened_at=time() - 31,
        ),
        breaker.policy.state_ttl_seconds,
    )

    result = breaker.call(success)
    snapshot = breaker.get_snapshot()

    assert result == "ok"
    assert snapshot.state == CircuitState.HALF_OPEN
    assert snapshot.success_count == 1
    assert snapshot.half_open_calls == 0


def test_half_open_closes_after_success_threshold(
    breaker,
    repository,
):
    repository.save(
        CircuitBreakerSnapshot(
            name=breaker.name,
            state=CircuitState.HALF_OPEN,
            success_count=1,
            half_open_calls=0,
            opened_at=time() - 31,
        ),
        breaker.policy.state_ttl_seconds,
    )

    result = breaker.call(success)
    snapshot = breaker.get_snapshot()

    assert result == "ok"
    assert snapshot.state == CircuitState.CLOSED
    assert snapshot.failure_count == 0
    assert snapshot.success_count == 0
    assert snapshot.half_open_calls == 0
    assert snapshot.opened_at is None


def test_reset_returns_breaker_to_closed(
    breaker,
    repository,
):
    repository.save(
        CircuitBreakerSnapshot(
            name=breaker.name,
            state=CircuitState.OPEN,
            failure_count=5,
            opened_at=time(),
        ),
        breaker.policy.state_ttl_seconds,
    )

    snapshot = breaker.reset()

    assert snapshot.state == CircuitState.CLOSED
    assert snapshot.failure_count == 0
    assert snapshot.success_count == 0
    assert snapshot.half_open_calls == 0
    assert snapshot.opened_at is None

    persisted = breaker.get_snapshot()
    assert persisted.state == CircuitState.CLOSED
    
def test_half_open_rejects_when_probe_limit_is_reached(
    breaker,
    repository,
):
    repository.save(
        CircuitBreakerSnapshot(
            name=breaker.name,
            state=CircuitState.HALF_OPEN,
            success_count=0,
            half_open_calls=breaker.policy.half_open_max_calls,
            opened_at=time() - 31,
        ),
        breaker.policy.state_ttl_seconds,
    )

    with pytest.raises(CircuitBreakerOpenError) as exc_info:
        breaker.call(success)

    assert exc_info.value.breaker_name == breaker.name

    snapshot = breaker.get_snapshot()

    assert snapshot.state == CircuitState.HALF_OPEN
    assert (
        snapshot.half_open_calls
        == breaker.policy.half_open_max_calls
    )
    
def transition_metric_value(
    breaker_name: str,
    from_state: CircuitState,
    to_state: CircuitState,
) -> float:
    return CIRCUIT_BREAKER_TRANSITIONS.labels(
        breaker=breaker_name,
        from_state=from_state.value,
        to_state=to_state.value,
    )._value.get()


def rejection_metric_value(breaker_name: str) -> float:
    return CIRCUIT_BREAKER_REJECTIONS.labels(
        breaker=breaker_name,
    )._value.get()


def state_metric_value(breaker_name: str) -> float:
    return CIRCUIT_BREAKER_STATE.labels(
        breaker=breaker_name,
    )._value.get()
    
def test_closed_to_open_transition_increments_counter_once(
    policy,
    repository,
):
    breaker_name = "test.metric.closed-to-open"

    breaker = CircuitBreaker(
        name=breaker_name,
        policy=policy,
        repository=repository,
    )

    before = transition_metric_value(
        breaker_name,
        CircuitState.CLOSED,
        CircuitState.OPEN,
    )

    for _ in range(policy.failure_threshold):
        with pytest.raises(RuntimeError):
            breaker.call(failure)

    after = transition_metric_value(
        breaker_name,
        CircuitState.CLOSED,
        CircuitState.OPEN,
    )

    assert after == before + 1
    
def test_state_gauge_reflects_open_state(
    policy,
    repository,
):
    breaker_name = "test.metric.state-open"

    breaker = CircuitBreaker(
        name=breaker_name,
        policy=policy,
        repository=repository,
    )

    for _ in range(policy.failure_threshold):
        with pytest.raises(RuntimeError):
            breaker.call(failure)

    assert state_metric_value(breaker_name) == STATE_NUMERIC_VALUE[
        CircuitState.OPEN.value
    ]

def test_open_rejection_increments_rejection_counter(
    policy,
    repository,
):
    breaker_name = "test.metric.rejection"

    breaker = CircuitBreaker(
        name=breaker_name,
        policy=policy,
        repository=repository,
    )

    repository.save(
        CircuitBreakerSnapshot(
            name=breaker_name,
            state=CircuitState.OPEN,
            failure_count=policy.failure_threshold,
            opened_at=time(),
        ),
        policy.state_ttl_seconds,
    )

    before = rejection_metric_value(breaker_name)

    with pytest.raises(CircuitBreakerOpenError):
        breaker.call(success)

    after = rejection_metric_value(breaker_name)

    assert after == before + 1
    

