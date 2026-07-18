class CircuitBreakerError(RuntimeError):
    """Base exception for circuit-breaker failures."""


class CircuitBreakerOpenError(CircuitBreakerError):
    def __init__(
        self,
        breaker_name: str,
        retry_after_seconds: float,
    ) -> None:
        self.breaker_name = breaker_name
        self.retry_after_seconds = max(
            0.0,
            retry_after_seconds,
        )

        super().__init__(
            f"Circuit breaker '{breaker_name}' is open. "
            f"Retry after approximately "
            f"{self.retry_after_seconds:.2f} seconds."
        )


class CircuitBreakerStorageError(CircuitBreakerError):
    """Raised when distributed breaker state cannot be accessed."""