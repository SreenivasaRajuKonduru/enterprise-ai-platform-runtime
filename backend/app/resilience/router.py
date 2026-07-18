from fastapi import APIRouter, HTTPException, status

from backend.app.resilience.registry import (
    ollama_circuit_breaker,
)

router = APIRouter(
    prefix="/ops/circuit-breakers",
    tags=["Circuit Breakers"],
)


def _serialize_snapshot(snapshot) -> dict:
    return {
        "name": snapshot.name,
        "state": snapshot.state.value,
        "failure_count": snapshot.failure_count,
        "success_count": snapshot.success_count,
        "half_open_calls": snapshot.half_open_calls,
        "opened_at": snapshot.opened_at,
        "updated_at": snapshot.updated_at,
    }


@router.get("")
def list_circuit_breakers():
    snapshot = ollama_circuit_breaker.get_snapshot()

    return {
        "circuit_breakers": [
            _serialize_snapshot(snapshot)
        ]
    }


@router.get("/{breaker_name}")
def get_circuit_breaker(breaker_name: str):
    if breaker_name != ollama_circuit_breaker.name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Circuit breaker not found",
        )

    return _serialize_snapshot(
        ollama_circuit_breaker.get_snapshot()
    )


@router.post("/{breaker_name}/reset")
def reset_circuit_breaker(breaker_name: str):
    if breaker_name != ollama_circuit_breaker.name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Circuit breaker not found",
        )

    return {
        "message": "Circuit breaker reset successfully",
        "circuit_breaker": _serialize_snapshot(
            ollama_circuit_breaker.reset()
        ),
    }