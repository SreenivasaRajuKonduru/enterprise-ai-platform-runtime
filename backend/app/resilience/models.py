from dataclasses import dataclass
from enum import StrEnum
from time import time


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class CircuitBreakerPolicy:
    failure_threshold: int
    recovery_timeout_seconds: int
    half_open_max_calls: int
    success_threshold: int
    state_ttl_seconds: int
    lock_timeout_seconds: int


@dataclass
class CircuitBreakerSnapshot:
    name: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    half_open_calls: int = 0
    opened_at: float | None = None
    updated_at: float = 0.0

    @classmethod
    def new(cls, name: str) -> "CircuitBreakerSnapshot":
        return cls(
            name=name,
            updated_at=time(),
        )