from prometheus_client import Counter, Gauge, Histogram


CIRCUIT_BREAKER_CALLS = Counter(
    "circuit_breaker_calls_total",
    "Total calls passing through a circuit breaker",
    ["breaker", "result"],
)

CIRCUIT_BREAKER_REJECTIONS = Counter(
    "circuit_breaker_rejections_total",
    "Calls rejected because a circuit breaker is open",
    ["breaker"],
)

CIRCUIT_BREAKER_TRANSITIONS = Counter(
    "circuit_breaker_transitions_total",
    "Circuit-breaker state transitions",
    ["breaker", "from_state", "to_state"],
)

CIRCUIT_BREAKER_STATE = Gauge(
    "circuit_breaker_state",
    (
        "Current circuit-breaker state: "
        "0=closed, 1=half_open, 2=open"
    ),
    ["breaker"],
)

CIRCUIT_BREAKER_EXECUTION_SECONDS = Histogram(
    "circuit_breaker_execution_seconds",
    "Duration of protected calls",
    ["breaker", "result"],
)


STATE_NUMERIC_VALUE = {
    "closed": 0,
    "half_open": 1,
    "open": 2,
}