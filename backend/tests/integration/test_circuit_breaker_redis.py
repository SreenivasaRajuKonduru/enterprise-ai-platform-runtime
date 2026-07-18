import os
import threading
from time import sleep, time
from uuid import uuid4

import pytest
from redis import Redis
from redis.exceptions import RedisError

from backend.app.resilience.exceptions import CircuitBreakerOpenError
from backend.app.resilience.models import (
    CircuitBreakerPolicy,
    CircuitBreakerSnapshot,
    CircuitState,
)
from backend.app.resilience.repository import CircuitBreakerRepository
from backend.app.resilience.service import CircuitBreaker


def failing_operation():
    raise RuntimeError("dependency unavailable")


def successful_operation():
    return "ok"


@pytest.fixture(scope="session")
def redis_client():
    redis_url = os.getenv(
        "TEST_REDIS_URL",
        "redis://localhost:6379/15",
    )

    client = Redis.from_url(
        redis_url,
        decode_responses=False,
        socket_connect_timeout=2,
        socket_timeout=2,
    )

    try:
        client.ping()
    except RedisError:
        pytest.skip(
            f"Redis integration tests require Redis at {redis_url}"
        )

    yield client

    client.close()


@pytest.fixture
def namespace(redis_client):
    value = f"test_circuit_breaker:{uuid4().hex}"

    yield value

    for key in redis_client.scan_iter(f"{value}:*"):
        redis_client.delete(key)


@pytest.fixture
def policy():
    return CircuitBreakerPolicy(
        failure_threshold=3,
        recovery_timeout_seconds=30,
        half_open_max_calls=1,
        success_threshold=2,
        state_ttl_seconds=300,
        lock_timeout_seconds=5,
    )


@pytest.fixture
def repositories(redis_client, namespace):
    repository_a = CircuitBreakerRepository(
        redis_client=redis_client,
        namespace=namespace,
    )

    repository_b = CircuitBreakerRepository(
        redis_client=redis_client,
        namespace=namespace,
    )

    return repository_a, repository_b


def test_snapshot_is_serialized_and_loaded_from_redis(
    repositories,
    policy,
):
    repository_a, repository_b = repositories
    breaker_name = "serialization-test"

    expected = CircuitBreakerSnapshot(
        name=breaker_name,
        state=CircuitState.HALF_OPEN,
        failure_count=3,
        success_count=1,
        half_open_calls=1,
        opened_at=time() - 30,
    )

    repository_a.save(
        expected,
        ttl_seconds=policy.state_ttl_seconds,
    )

    actual = repository_b.get(breaker_name)

    assert actual.name == breaker_name
    assert actual.state == CircuitState.HALF_OPEN
    assert actual.failure_count == 3
    assert actual.success_count == 1
    assert actual.half_open_calls == 1
    assert actual.opened_at == pytest.approx(
        expected.opened_at,
    )
    assert actual.updated_at > 0


def test_two_breakers_share_open_state_through_redis(
    repositories,
    policy,
):
    repository_a, repository_b = repositories
    breaker_name = "shared-open-state"

    breaker_a = CircuitBreaker(
        name=breaker_name,
        policy=policy,
        repository=repository_a,
    )

    breaker_b = CircuitBreaker(
        name=breaker_name,
        policy=policy,
        repository=repository_b,
    )

    for _ in range(policy.failure_threshold):
        with pytest.raises(RuntimeError):
            breaker_a.call(failing_operation)

    snapshot = breaker_b.get_snapshot()

    assert snapshot.state == CircuitState.OPEN
    assert snapshot.failure_count == policy.failure_threshold
    assert snapshot.opened_at is not None

    with pytest.raises(CircuitBreakerOpenError):
        breaker_b.call(successful_operation)


def test_reset_is_visible_to_another_breaker_instance(
    repositories,
    policy,
):
    repository_a, repository_b = repositories
    breaker_name = "shared-reset-state"

    breaker_a = CircuitBreaker(
        name=breaker_name,
        policy=policy,
        repository=repository_a,
    )

    breaker_b = CircuitBreaker(
        name=breaker_name,
        policy=policy,
        repository=repository_b,
    )

    for _ in range(policy.failure_threshold):
        with pytest.raises(RuntimeError):
            breaker_a.call(failing_operation)

    assert (
        breaker_b.get_snapshot().state
        == CircuitState.OPEN
    )

    breaker_b.reset()

    snapshot = breaker_a.get_snapshot()

    assert snapshot.state == CircuitState.CLOSED
    assert snapshot.failure_count == 0
    assert snapshot.success_count == 0
    assert snapshot.half_open_calls == 0
    assert snapshot.opened_at is None

    assert breaker_a.call(successful_operation) == "ok"


def test_distributed_lock_serializes_repository_access(
    repositories,
):
    repository_a, repository_b = repositories
    breaker_name = "distributed-lock-test"

    first_acquired = threading.Event()
    release_first = threading.Event()
    second_acquired = threading.Event()
    acquisition_order = []

    def first_worker():
        with repository_a.lock(
            breaker_name,
            timeout_seconds=5,
        ):
            acquisition_order.append("first")
            first_acquired.set()
            release_first.wait(timeout=3)

    def second_worker():
        first_acquired.wait(timeout=3)

        with repository_b.lock(
            breaker_name,
            timeout_seconds=5,
        ):
            acquisition_order.append("second")
            second_acquired.set()

    first_thread = threading.Thread(
        target=first_worker,
        daemon=True,
    )
    second_thread = threading.Thread(
        target=second_worker,
        daemon=True,
    )

    first_thread.start()
    second_thread.start()

    assert first_acquired.wait(timeout=2)

    sleep(0.2)

    assert not second_acquired.is_set()

    release_first.set()

    first_thread.join(timeout=3)
    second_thread.join(timeout=3)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert second_acquired.is_set()
    assert acquisition_order == ["first", "second"]


def test_repository_delete_removes_shared_redis_state(
    repositories,
    policy,
):
    repository_a, repository_b = repositories
    breaker_name = "shared-delete-state"

    repository_a.save(
        CircuitBreakerSnapshot(
            name=breaker_name,
            state=CircuitState.OPEN,
            failure_count=policy.failure_threshold,
            opened_at=time(),
        ),
        ttl_seconds=policy.state_ttl_seconds,
    )

    assert (
        repository_b.get(breaker_name).state
        == CircuitState.OPEN
    )

    repository_a.delete(breaker_name)

    snapshot = repository_b.get(breaker_name)

    assert snapshot.state == CircuitState.CLOSED
    assert snapshot.failure_count == 0