import logging
from collections.abc import Callable
from time import perf_counter, time
from typing import ParamSpec, TypeVar

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from backend.app.resilience.exceptions import (
    CircuitBreakerOpenError,
)
from backend.app.resilience.metrics import (
    CIRCUIT_BREAKER_CALLS,
    CIRCUIT_BREAKER_EXECUTION_SECONDS,
    CIRCUIT_BREAKER_REJECTIONS,
    CIRCUIT_BREAKER_STATE,
    CIRCUIT_BREAKER_TRANSITIONS,
    STATE_NUMERIC_VALUE,
)
from backend.app.resilience.models import (
    CircuitBreakerPolicy,
    CircuitBreakerSnapshot,
    CircuitState,
)
from backend.app.resilience.repository import (
    CircuitBreakerRepository,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        policy: CircuitBreakerPolicy,
        repository: CircuitBreakerRepository,
        enabled: bool = True,
        failure_exceptions: tuple[
            type[BaseException],
            ...,
        ] = (Exception,),
        ignored_exceptions: tuple[
            type[BaseException],
            ...,
        ] = (),
    ) -> None:
        self.name = name
        self.policy = policy
        self.repository = repository
        self.enabled = enabled
        self.failure_exceptions = failure_exceptions
        self.ignored_exceptions = ignored_exceptions

    def call(
        self,
        operation: Callable[P, T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        if not self.enabled:
            return operation(*args, **kwargs)

        with tracer.start_as_current_span(
            "circuit_breaker.call",
            attributes={
                "circuit_breaker.name": self.name,
            },
        ) as span:
            self._before_call(span)

            start_time = perf_counter()

            try:
                result = operation(*args, **kwargs)

            except self.ignored_exceptions:
                self._record_success()

                CIRCUIT_BREAKER_CALLS.labels(
                    breaker=self.name,
                    result="ignored_exception",
                ).inc()

                raise

            except self.failure_exceptions as exc:
                duration = perf_counter() - start_time

                CIRCUIT_BREAKER_EXECUTION_SECONDS.labels(
                    breaker=self.name,
                    result="failure",
                ).observe(duration)

                CIRCUIT_BREAKER_CALLS.labels(
                    breaker=self.name,
                    result="failure",
                ).inc()

                self._record_failure(exc)

                span.record_exception(exc)
                span.set_status(
                    Status(
                        StatusCode.ERROR,
                        str(exc),
                    )
                )

                raise

            except BaseException:
                self._record_success()
                raise

            duration = perf_counter() - start_time

            CIRCUIT_BREAKER_EXECUTION_SECONDS.labels(
                breaker=self.name,
                result="success",
            ).observe(duration)

            CIRCUIT_BREAKER_CALLS.labels(
                breaker=self.name,
                result="success",
            ).inc()

            self._record_success()

            span.set_status(Status(StatusCode.OK))

            return result

    def get_snapshot(self) -> CircuitBreakerSnapshot:
        snapshot = self.repository.get(self.name)
        self._publish_state_metric(snapshot)
        return snapshot

    def reset(self) -> CircuitBreakerSnapshot:
        with self.repository.lock(
            self.name,
            self.policy.lock_timeout_seconds,
        ):
            previous = self.repository.get(self.name)
            snapshot = CircuitBreakerSnapshot.new(self.name)

            self.repository.save(
                snapshot,
                self.policy.state_ttl_seconds,
            )

            self._record_transition(
                previous.state,
                snapshot.state,
            )

            logger.info(
                "circuit_breaker_reset",
                extra={
                    "breaker": self.name,
                    "previous_state": previous.state.value,
                },
            )

            return snapshot

    def _before_call(self, span) -> None:
        with self.repository.lock(
            self.name,
            self.policy.lock_timeout_seconds,
        ):
            snapshot = self.repository.get(self.name)
            now = time()

            span.set_attribute(
                "circuit_breaker.state",
                snapshot.state.value,
            )

            if snapshot.state == CircuitState.OPEN:
                opened_at = snapshot.opened_at or now

                elapsed = now - opened_at

                if elapsed < (
                    self.policy.recovery_timeout_seconds
                ):
                    retry_after = (
                        self.policy.recovery_timeout_seconds
                        - elapsed
                    )

                    CIRCUIT_BREAKER_REJECTIONS.labels(
                        breaker=self.name
                    ).inc()

                    span.set_attribute(
                        "circuit_breaker.rejected",
                        True,
                    )

                    raise CircuitBreakerOpenError(
                        breaker_name=self.name,
                        retry_after_seconds=retry_after,
                    )

                previous_state = snapshot.state
                snapshot.state = CircuitState.HALF_OPEN
                snapshot.failure_count = 0
                snapshot.success_count = 0
                snapshot.half_open_calls = 0

                self._record_transition(
                    previous_state,
                    snapshot.state,
                )

            if snapshot.state == CircuitState.HALF_OPEN:
                if (
                    snapshot.half_open_calls
                    >= self.policy.half_open_max_calls
                ):
                    CIRCUIT_BREAKER_REJECTIONS.labels(
                        breaker=self.name
                    ).inc()

                    raise CircuitBreakerOpenError(
                        breaker_name=self.name,
                        retry_after_seconds=1,
                    )

                snapshot.half_open_calls += 1

            self.repository.save(
                snapshot,
                self.policy.state_ttl_seconds,
            )

            self._publish_state_metric(snapshot)

    def _record_success(self) -> None:
        with self.repository.lock(
            self.name,
            self.policy.lock_timeout_seconds,
        ):
            snapshot = self.repository.get(self.name)

            if snapshot.state == CircuitState.CLOSED:
                snapshot.failure_count = 0
                snapshot.success_count = 0

            elif snapshot.state == CircuitState.HALF_OPEN:
                snapshot.success_count += 1
                snapshot.half_open_calls = max(
                    0,
                    snapshot.half_open_calls - 1,
                )

                if (
                    snapshot.success_count
                    >= self.policy.success_threshold
                ):
                    previous_state = snapshot.state

                    snapshot.state = CircuitState.CLOSED
                    snapshot.failure_count = 0
                    snapshot.success_count = 0
                    snapshot.half_open_calls = 0
                    snapshot.opened_at = None

                    self._record_transition(
                        previous_state,
                        snapshot.state,
                    )

            self.repository.save(
                snapshot,
                self.policy.state_ttl_seconds,
            )

            self._publish_state_metric(snapshot)

    def _record_failure(
        self,
        exception: BaseException,
    ) -> None:
        with self.repository.lock(
            self.name,
            self.policy.lock_timeout_seconds,
        ):
            snapshot = self.repository.get(self.name)

            if snapshot.state == CircuitState.HALF_OPEN:
                previous_state = snapshot.state

                snapshot.state = CircuitState.OPEN
                snapshot.failure_count += 1
                snapshot.success_count = 0
                snapshot.half_open_calls = 0
                snapshot.opened_at = time()

                self._record_transition(
                    previous_state,
                    snapshot.state,
                )

            else:
                snapshot.failure_count += 1

                if (
                    snapshot.failure_count
                    >= self.policy.failure_threshold
                ):
                    previous_state = snapshot.state

                    snapshot.state = CircuitState.OPEN
                    snapshot.opened_at = time()
                    snapshot.success_count = 0
                    snapshot.half_open_calls = 0

                    self._record_transition(
                        previous_state,
                        snapshot.state,
                    )

            self.repository.save(
                snapshot,
                self.policy.state_ttl_seconds,
            )

            self._publish_state_metric(snapshot)

            logger.warning(
                "circuit_breaker_failure_recorded",
                extra={
                    "breaker": self.name,
                    "state": snapshot.state.value,
                    "failure_count": snapshot.failure_count,
                    "exception_type": type(exception).__name__,
                    "exception_message": str(exception),
                },
            )

    def _record_transition(
        self,
        previous: CircuitState,
        current: CircuitState,
    ) -> None:
        if previous == current:
            return

        CIRCUIT_BREAKER_TRANSITIONS.labels(
            breaker=self.name,
            from_state=previous.value,
            to_state=current.value,
        ).inc()

        logger.info(
            "circuit_breaker_state_transition",
            extra={
                "breaker": self.name,
                "from_state": previous.value,
                "to_state": current.value,
            },
        )

    def _publish_state_metric(
        self,
        snapshot: CircuitBreakerSnapshot,
    ) -> None:
        CIRCUIT_BREAKER_STATE.labels(
            breaker=self.name
        ).set(
            STATE_NUMERIC_VALUE[snapshot.state.value]
        )