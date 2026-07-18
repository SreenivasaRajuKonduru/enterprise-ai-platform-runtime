from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.resilience.models import (
    CircuitBreakerSnapshot,
    CircuitState,
)
from backend.app.resilience.router import router
import backend.app.resilience.router as router_module


@pytest.fixture
def breaker():
    mock_breaker = Mock()
    mock_breaker.name = "ollama.generate"

    mock_breaker.get_snapshot.return_value = (
        CircuitBreakerSnapshot(
            name="ollama.generate",
            state=CircuitState.OPEN,
            failure_count=3,
            success_count=1,
            half_open_calls=2,
            opened_at=100.0,
            updated_at=200.0,
        )
    )

    mock_breaker.reset.return_value = (
        CircuitBreakerSnapshot(
            name="ollama.generate",
            state=CircuitState.CLOSED,
            failure_count=0,
            success_count=0,
            half_open_calls=0,
            opened_at=None,
            updated_at=300.0,
        )
    )

    return mock_breaker


@pytest.fixture
def client(monkeypatch, breaker):
    monkeypatch.setattr(
        router_module,
        "ollama_circuit_breaker",
        breaker,
    )

    app = FastAPI()
    app.include_router(router)

    return TestClient(app)


def test_list_circuit_breakers(client, breaker):
    response = client.get(
        "/ops/circuit-breakers"
    )

    assert response.status_code == 200
    assert response.json() == {
        "circuit_breakers": [
            {
                "name": "ollama.generate",
                "state": "open",
                "failure_count": 3,
                "success_count": 1,
                "half_open_calls": 2,
                "opened_at": 100.0,
                "updated_at": 200.0,
            }
        ]
    }

    breaker.get_snapshot.assert_called_once_with()


def test_get_circuit_breaker(client, breaker):
    response = client.get(
        "/ops/circuit-breakers/ollama.generate"
    )

    assert response.status_code == 200
    assert response.json()["name"] == "ollama.generate"
    assert response.json()["state"] == "open"
    assert response.json()["failure_count"] == 3

    breaker.get_snapshot.assert_called_once_with()


def test_get_unknown_circuit_breaker_returns_404(
    client,
    breaker,
):
    response = client.get(
        "/ops/circuit-breakers/unknown.breaker"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Circuit breaker not found"
    }

    breaker.get_snapshot.assert_not_called()


def test_reset_circuit_breaker(client, breaker):
    response = client.post(
        "/ops/circuit-breakers/"
        "ollama.generate/reset"
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": (
            "Circuit breaker reset successfully"
        ),
        "circuit_breaker": {
            "name": "ollama.generate",
            "state": "closed",
            "failure_count": 0,
            "success_count": 0,
            "half_open_calls": 0,
            "opened_at": None,
            "updated_at": 300.0,
        },
    }

    breaker.reset.assert_called_once_with()


def test_reset_unknown_circuit_breaker_returns_404(
    client,
    breaker,
):
    response = client.post(
        "/ops/circuit-breakers/"
        "unknown.breaker/reset"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Circuit breaker not found"
    }

    breaker.reset.assert_not_called()
