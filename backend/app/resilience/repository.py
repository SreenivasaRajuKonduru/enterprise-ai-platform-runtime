import json
import logging
import threading
from contextlib import contextmanager
from time import time
from typing import Iterator

from redis import Redis
from redis.exceptions import RedisError

from backend.app.resilience.models import (
    CircuitBreakerSnapshot,
    CircuitState,
)

logger = logging.getLogger(__name__)


class CircuitBreakerRepository:
    def __init__(
        self,
        redis_client: Redis,
        namespace: str = "circuit_breaker",
    ) -> None:
        self._redis = redis_client
        self._namespace = namespace
        self._local_state: dict[
            str,
            CircuitBreakerSnapshot,
        ] = {}
        self._local_locks: dict[str, threading.RLock] = {}
        self._guard = threading.Lock()

    def _state_key(self, name: str) -> str:
        return f"{self._namespace}:state:{name}"

    def _lock_key(self, name: str) -> str:
        return f"{self._namespace}:lock:{name}"

    def _get_local_lock(self, name: str) -> threading.RLock:
        with self._guard:
            lock = self._local_locks.get(name)

            if lock is None:
                lock = threading.RLock()
                self._local_locks[name] = lock

            return lock

    @contextmanager
    def lock(
        self,
        name: str,
        timeout_seconds: int,
    ) -> Iterator[None]:
        try:
            distributed_lock = self._redis.lock(
                self._lock_key(name),
                timeout=timeout_seconds,
                blocking_timeout=timeout_seconds,
            )

            acquired = distributed_lock.acquire(
                blocking=True,
            )

            if not acquired:
                raise TimeoutError(
                    f"Unable to acquire circuit-breaker lock "
                    f"for '{name}'"
                )

            try:
                yield
            finally:
                try:
                    distributed_lock.release()
                except RedisError:
                    logger.exception(
                        "circuit_breaker_lock_release_failed",
                        extra={
                            "breaker": name,
                        },
                    )

        except (RedisError, TimeoutError):
            logger.warning(
                "circuit_breaker_using_local_lock",
                extra={
                    "breaker": name,
                },
            )

            local_lock = self._get_local_lock(name)

            with local_lock:
                yield

    def get(self, name: str) -> CircuitBreakerSnapshot:
        try:
            raw_value = self._redis.get(
                self._state_key(name)
            )

            if raw_value is None:
                return CircuitBreakerSnapshot.new(name)

            if isinstance(raw_value, bytes):
                raw_value = raw_value.decode("utf-8")

            payload = json.loads(raw_value)

            return self._deserialize(name, payload)

        except (RedisError, ValueError, TypeError):
            logger.exception(
                "circuit_breaker_redis_read_failed",
                extra={
                    "breaker": name,
                },
            )

            return self._local_state.get(
                name,
                CircuitBreakerSnapshot.new(name),
            )

    def save(
        self,
        snapshot: CircuitBreakerSnapshot,
        ttl_seconds: int,
    ) -> None:
        snapshot.updated_at = time()
        payload = self._serialize(snapshot)

        self._local_state[snapshot.name] = snapshot

        try:
            self._redis.set(
                self._state_key(snapshot.name),
                json.dumps(payload),
                ex=ttl_seconds,
            )

        except RedisError:
            logger.exception(
                "circuit_breaker_redis_write_failed",
                extra={
                    "breaker": snapshot.name,
                    "state": snapshot.state.value,
                },
            )

    def delete(self, name: str) -> None:
        self._local_state.pop(name, None)

        try:
            self._redis.delete(self._state_key(name))

        except RedisError:
            logger.exception(
                "circuit_breaker_redis_delete_failed",
                extra={
                    "breaker": name,
                },
            )

    @staticmethod
    def _serialize(
        snapshot: CircuitBreakerSnapshot,
    ) -> dict:
        return {
            "state": snapshot.state.value,
            "failure_count": snapshot.failure_count,
            "success_count": snapshot.success_count,
            "half_open_calls": snapshot.half_open_calls,
            "opened_at": snapshot.opened_at,
            "updated_at": snapshot.updated_at,
        }

    @staticmethod
    def _deserialize(
        name: str,
        payload: dict,
    ) -> CircuitBreakerSnapshot:
        return CircuitBreakerSnapshot(
            name=name,
            state=CircuitState(
                payload.get(
                    "state",
                    CircuitState.CLOSED.value,
                )
            ),
            failure_count=int(
                payload.get("failure_count", 0)
            ),
            success_count=int(
                payload.get("success_count", 0)
            ),
            half_open_calls=int(
                payload.get("half_open_calls", 0)
            ),
            opened_at=payload.get("opened_at"),
            updated_at=float(
                payload.get("updated_at", time())
            ),
        )