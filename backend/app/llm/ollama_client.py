import logging
from time import perf_counter

import requests
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from backend.app.core.config import settings
from backend.app.resilience.registry import (
    ollama_circuit_breaker,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class OllamaResponseError(RuntimeError):
    pass


def _perform_generation(prompt: str) -> str:
    response = requests.post(
        settings.ollama_url,
        json={
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,
        },
        timeout=settings.ollama_timeout_seconds,
    )

    response.raise_for_status()

    response_body = response.json()
    answer = response_body.get("response")

    if not isinstance(answer, str) or not answer.strip():
        raise OllamaResponseError(
            "Ollama returned an empty or invalid response"
        )

    return answer


def generate_answer(prompt: str) -> str:
    if not prompt or not prompt.strip():
        raise ValueError("Prompt must not be empty")

    with tracer.start_as_current_span(
        "rag.generate",
        attributes={
            "gen_ai.provider.name": "ollama",
            "gen_ai.request.model": settings.ollama_model,
            "gen_ai.operation.name": "generate",
            "gen_ai.prompt.length": len(prompt),
            "circuit_breaker.name": "ollama.generate",
        },
    ) as span:
        start_time = perf_counter()

        try:
            answer = ollama_circuit_breaker.call(
                _perform_generation,
                prompt,
            )

            latency_ms = round(
                (perf_counter() - start_time) * 1000,
                2,
            )

            span.set_attribute(
                "gen_ai.response.length",
                len(answer),
            )
            span.set_attribute(
                "gen_ai.response.latency_ms",
                latency_ms,
            )
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "ollama_generation_completed",
                extra={
                    "model": settings.ollama_model,
                    "prompt_length": len(prompt),
                    "response_length": len(answer),
                    "latency_ms": latency_ms,
                },
            )

            return answer

        except Exception as exc:
            latency_ms = round(
                (perf_counter() - start_time) * 1000,
                2,
            )

            span.set_attribute(
                "gen_ai.response.latency_ms",
                latency_ms,
            )
            span.record_exception(exc)
            span.set_status(
                Status(
                    StatusCode.ERROR,
                    str(exc),
                )
            )

            logger.exception(
                "ollama_generation_failed",
                extra={
                    "model": settings.ollama_model,
                    "prompt_length": len(prompt),
                    "latency_ms": latency_ms,
                    "exception_type": type(exc).__name__,
                },
            )

            raise