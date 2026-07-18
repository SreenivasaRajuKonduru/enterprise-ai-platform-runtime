from backend.app.resilience.registry import (
    default_policy,
    ollama_circuit_breaker,
    repository,
)
from backend.app.resilience.repository import (
    CircuitBreakerRepository,
)
from backend.app.resilience.service import CircuitBreaker


def test_registry_creates_repository():
    assert isinstance(repository, CircuitBreakerRepository)


def test_registry_creates_valid_default_policy():
    assert default_policy.failure_threshold > 0
    assert default_policy.recovery_timeout_seconds > 0
    assert default_policy.half_open_max_calls > 0
    assert default_policy.success_threshold > 0
    assert default_policy.state_ttl_seconds > 0
    assert default_policy.lock_timeout_seconds > 0


def test_registry_creates_ollama_circuit_breaker():
    assert isinstance(ollama_circuit_breaker, CircuitBreaker)
    assert ollama_circuit_breaker.name == "ollama.generate"
    assert ollama_circuit_breaker.policy is default_policy
    assert ollama_circuit_breaker.repository is repository


def test_registry_configures_expected_failure_exceptions():
    exception_types = (
        ollama_circuit_breaker.failure_exceptions
    )

    assert len(exception_types) == 3
    assert all(
        issubclass(exception_type, Exception)
        for exception_type in exception_types
    )
