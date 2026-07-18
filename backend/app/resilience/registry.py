import requests

from backend.app.core.config import settings
from backend.app.db.session import redis_client
from backend.app.resilience.models import (
    CircuitBreakerPolicy,
)
from backend.app.resilience.repository import (
    CircuitBreakerRepository,
)
from backend.app.resilience.service import CircuitBreaker


repository = CircuitBreakerRepository(
    redis_client=redis_client,
)

default_policy = CircuitBreakerPolicy(
    failure_threshold=(
        settings.circuit_breaker_failure_threshold
    ),
    recovery_timeout_seconds=(
        settings.circuit_breaker_recovery_timeout_seconds
    ),
    half_open_max_calls=(
        settings.circuit_breaker_half_open_max_calls
    ),
    success_threshold=(
        settings.circuit_breaker_success_threshold
    ),
    state_ttl_seconds=(
        settings.circuit_breaker_state_ttl_seconds
    ),
    lock_timeout_seconds=(
        settings.circuit_breaker_lock_timeout_seconds
    ),
)

ollama_circuit_breaker = CircuitBreaker(
    name="ollama.generate",
    policy=default_policy,
    repository=repository,
    enabled=settings.circuit_breaker_enabled,
    failure_exceptions=(
        requests.Timeout,
        requests.ConnectionError,
        requests.HTTPError,
    ),
)