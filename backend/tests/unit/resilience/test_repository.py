import json
from unittest.mock import Mock

import pytest
from redis.exceptions import RedisError

from backend.app.resilience.models import (
    CircuitBreakerSnapshot,
    CircuitState,
)
from backend.app.resilience.repository import (
    CircuitBreakerRepository,
)


@pytest.fixture
def redis_client():
    return Mock()


@pytest.fixture
def repository(redis_client):
    return CircuitBreakerRepository(
        redis_client=redis_client,
        namespace="test_breaker",
    )


def test_state_and_lock_keys(repository):
    assert (
        repository._state_key("ollama.generate")
        == "test_breaker:state:ollama.generate"
    )
    assert (
        repository._lock_key("ollama.generate")
        == "test_breaker:lock:ollama.generate"
    )


def test_get_returns_new_closed_snapshot_when_redis_key_missing(
    repository,
    redis_client,
):
    redis_client.get.return_value = None

    snapshot = repository.get("ollama.generate")

    assert snapshot.name == "ollama.generate"
    assert snapshot.state == CircuitState.CLOSED
    assert snapshot.failure_count == 0
    assert snapshot.success_count == 0
    assert snapshot.half_open_calls == 0
    assert snapshot.updated_at > 0


def test_get_deserializes_snapshot_from_redis_bytes(
    repository,
    redis_client,
):
    payload = {
        "state": "open",
        "failure_count": 3,
        "success_count": 1,
        "half_open_calls": 2,
        "opened_at": 100.5,
        "updated_at": 200.5,
    }
    redis_client.get.return_value = json.dumps(payload).encode(
        "utf-8"
    )

    snapshot = repository.get("ollama.generate")

    assert snapshot.name == "ollama.generate"
    assert snapshot.state == CircuitState.OPEN
    assert snapshot.failure_count == 3
    assert snapshot.success_count == 1
    assert snapshot.half_open_calls == 2
    assert snapshot.opened_at == 100.5
    assert snapshot.updated_at == 200.5


def test_get_deserializes_snapshot_from_redis_string(
    repository,
    redis_client,
):
    redis_client.get.return_value = json.dumps(
        {
            "state": "half_open",
            "failure_count": 0,
            "success_count": 1,
            "half_open_calls": 1,
            "opened_at": None,
            "updated_at": 300.0,
        }
    )

    snapshot = repository.get("ollama.generate")

    assert snapshot.state == CircuitState.HALF_OPEN
    assert snapshot.success_count == 1
    assert snapshot.half_open_calls == 1
    assert snapshot.updated_at == 300.0


def test_get_uses_default_values_for_partial_payload(
    repository,
    redis_client,
):
    redis_client.get.return_value = json.dumps({})

    snapshot = repository.get("ollama.generate")

    assert snapshot.name == "ollama.generate"
    assert snapshot.state == CircuitState.CLOSED
    assert snapshot.failure_count == 0
    assert snapshot.success_count == 0
    assert snapshot.half_open_calls == 0
    assert snapshot.opened_at is None
    assert snapshot.updated_at > 0


def test_get_falls_back_to_local_state_when_redis_read_fails(
    repository,
    redis_client,
):
    local_snapshot = CircuitBreakerSnapshot(
        name="ollama.generate",
        state=CircuitState.OPEN,
        failure_count=5,
        opened_at=123.0,
        updated_at=456.0,
    )
    repository._local_state["ollama.generate"] = local_snapshot
    redis_client.get.side_effect = RedisError(
        "redis unavailable"
    )

    snapshot = repository.get("ollama.generate")

    assert snapshot is local_snapshot
    assert snapshot.state == CircuitState.OPEN
    assert snapshot.failure_count == 5


def test_get_returns_new_snapshot_when_redis_payload_is_invalid(
    repository,
    redis_client,
):
    redis_client.get.return_value = "{not-valid-json"

    snapshot = repository.get("ollama.generate")

    assert snapshot.name == "ollama.generate"
    assert snapshot.state == CircuitState.CLOSED


def test_save_updates_timestamp_local_state_and_redis(
    repository,
    redis_client,
):
    snapshot = CircuitBreakerSnapshot(
        name="ollama.generate",
        state=CircuitState.OPEN,
        failure_count=3,
        opened_at=100.0,
    )

    repository.save(snapshot, ttl_seconds=120)

    assert snapshot.updated_at > 0
    assert repository._local_state["ollama.generate"] is snapshot

    redis_client.set.assert_called_once()

    key, raw_payload = redis_client.set.call_args.args
    assert key == "test_breaker:state:ollama.generate"

    stored_payload = json.loads(raw_payload)
    assert stored_payload["state"] == "open"
    assert stored_payload["failure_count"] == 3
    assert stored_payload["opened_at"] == 100.0

    assert redis_client.set.call_args.kwargs["ex"] == 120


def test_save_preserves_local_state_when_redis_write_fails(
    repository,
    redis_client,
):
    redis_client.set.side_effect = RedisError(
        "redis unavailable"
    )

    snapshot = CircuitBreakerSnapshot(
        name="ollama.generate",
        state=CircuitState.OPEN,
    )

    repository.save(snapshot, ttl_seconds=60)

    assert repository._local_state["ollama.generate"] is snapshot
    assert snapshot.updated_at > 0


def test_delete_removes_local_and_redis_state(
    repository,
    redis_client,
):
    repository._local_state[
        "ollama.generate"
    ] = CircuitBreakerSnapshot.new("ollama.generate")

    repository.delete("ollama.generate")

    assert "ollama.generate" not in repository._local_state
    redis_client.delete.assert_called_once_with(
        "test_breaker:state:ollama.generate"
    )


def test_delete_does_not_raise_when_redis_delete_fails(
    repository,
    redis_client,
):
    repository._local_state[
        "ollama.generate"
    ] = CircuitBreakerSnapshot.new("ollama.generate")
    redis_client.delete.side_effect = RedisError(
        "redis unavailable"
    )

    repository.delete("ollama.generate")

    assert "ollama.generate" not in repository._local_state


def test_distributed_lock_is_acquired_and_released(
    repository,
    redis_client,
):
    distributed_lock = Mock()
    distributed_lock.acquire.return_value = True
    redis_client.lock.return_value = distributed_lock

    executed = False

    with repository.lock(
        "ollama.generate",
        timeout_seconds=5,
    ):
        executed = True

    assert executed is True
    redis_client.lock.assert_called_once_with(
        "test_breaker:lock:ollama.generate",
        timeout=5,
        blocking_timeout=5,
    )
    distributed_lock.acquire.assert_called_once_with(
        blocking=True
    )
    distributed_lock.release.assert_called_once()


def test_lock_falls_back_to_local_lock_when_redis_fails(
    repository,
    redis_client,
):
    redis_client.lock.side_effect = RedisError(
        "redis unavailable"
    )

    executed = False

    with repository.lock(
        "ollama.generate",
        timeout_seconds=5,
    ):
        executed = True

    assert executed is True
    assert "ollama.generate" in repository._local_locks


def test_lock_falls_back_when_distributed_lock_times_out(
    repository,
    redis_client,
):
    distributed_lock = Mock()
    distributed_lock.acquire.return_value = False
    redis_client.lock.return_value = distributed_lock

    executed = False

    with repository.lock(
        "ollama.generate",
        timeout_seconds=5,
    ):
        executed = True

    assert executed is True
    assert "ollama.generate" in repository._local_locks
    distributed_lock.release.assert_not_called()


def test_release_failure_is_handled_without_interrupting_caller(
    repository,
    redis_client,
):
    distributed_lock = Mock()
    distributed_lock.acquire.return_value = True
    distributed_lock.release.side_effect = RedisError(
        "release failed"
    )
    redis_client.lock.return_value = distributed_lock

    with repository.lock(
        "ollama.generate",
        timeout_seconds=5,
    ):
        pass

    distributed_lock.release.assert_called_once()


def test_serialize_snapshot(repository):
    snapshot = CircuitBreakerSnapshot(
        name="ollama.generate",
        state=CircuitState.HALF_OPEN,
        failure_count=2,
        success_count=1,
        half_open_calls=1,
        opened_at=10.0,
        updated_at=20.0,
    )

    payload = repository._serialize(snapshot)

    assert payload == {
        "state": "half_open",
        "failure_count": 2,
        "success_count": 1,
        "half_open_calls": 1,
        "opened_at": 10.0,
        "updated_at": 20.0,
    }


def test_deserialize_snapshot(repository):
    snapshot = repository._deserialize(
        "ollama.generate",
        {
            "state": "open",
            "failure_count": "4",
            "success_count": "2",
            "half_open_calls": "1",
            "opened_at": 15.5,
            "updated_at": "25.5",
        },
    )

    assert snapshot.name == "ollama.generate"
    assert snapshot.state == CircuitState.OPEN
    assert snapshot.failure_count == 4
    assert snapshot.success_count == 2
    assert snapshot.half_open_calls == 1
    assert snapshot.opened_at == 15.5
    assert snapshot.updated_at == 25.5
