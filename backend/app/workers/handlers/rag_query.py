from typing import Any

from sqlalchemy.orm import Session

from backend.app.rag.answer_service import (
    generate_rag_answer,
)


def handle_rag_query(
    db: Session,
    payload: dict[str, Any],
) -> dict[str, Any]:
    question = payload.get("question")

    if not isinstance(question, str) or not question.strip():
        raise ValueError(
            "RAG_QUERY payload must contain a non-empty question."
        )

    result = generate_rag_answer(
        db=db,
        question=question.strip(),
    )

    return {
        **result,
        "handler": "rag_query",
        "execution_mode": "async_kafka_worker",
    }