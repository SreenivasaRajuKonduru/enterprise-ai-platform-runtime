import re
from time import perf_counter

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from sqlalchemy.orm import Session

from backend.app.llm.ollama_client import generate_answer
from backend.app.rag.retriever import retrieve_relevant_chunks

tracer = trace.get_tracer(__name__)

MODEL_NAME = "llama3.2"
PROVIDER_NAME = "ollama"
RETRIEVAL_LIMIT = 3


def generate_rag_answer(
    db: Session,
    question: str,
) -> dict:
    with tracer.start_as_current_span(
        "rag.answer",
        attributes={
            "rag.operation": "answer",
            "rag.question.length": len(question),
            "rag.retrieval.limit": RETRIEVAL_LIMIT,
            "gen_ai.provider.name": PROVIDER_NAME,
            "gen_ai.request.model": MODEL_NAME,
        },
    ) as answer_span:
        try:
            chunks = retrieve_relevant_chunks(
                db=db,
                query=question,
                limit=RETRIEVAL_LIMIT,
            )

            answer_span.set_attribute(
                "rag.retrieval.count",
                len(chunks),
            )

            context = "\n\n".join(
                row["content"]
                for row in chunks
            )

            if not context:
                answer_span.set_attribute(
                    "rag.grounded",
                    False,
                )
                answer_span.set_status(
                    Status(StatusCode.OK)
                )

                return {
                    "question": question,
                    "answer": (
                        "The provided context does not contain "
                        "enough information."
                    ),
                    "sources": [],
                    "metadata": {
                        "model": MODEL_NAME,
                        "provider": PROVIDER_NAME,
                        "retrieval_count": 0,
                        "generation_latency_ms": 0,
                        "grounded": False,
                    },
                }

            prompt = f"""
Answer the question using only the provided context.

Formatting rules:
- Return a concise bullet list.
- Preserve connected concepts in the same bullet.
- Do not split a technology from the feature it supports.
- Do not add information not present in the context.

Context:
{context}

Question:
{question}

Answer:
""".strip()

            start_time = perf_counter()

            try:
                answer = generate_answer(prompt)

                answer = re.sub(
                    r"\bRAG\s+[Mm]emory\b",
                    (
                        "Retrieval-Augmented Generation "
                        "(RAG) memory"
                    ),
                    answer,
                )

                grounded = True

            except Exception as exc:
                answer_span.record_exception(exc)

                answer = (
                    "LLM generation failed. Returning retrieved "
                    "context instead:\n\n"
                    f"{context}"
                )
                grounded = False

            latency_ms = round(
                (perf_counter() - start_time) * 1000,
                2,
            )

            answer_span.set_attribute(
                "rag.grounded",
                grounded,
            )
            answer_span.set_attribute(
                "gen_ai.response.latency_ms",
                latency_ms,
            )
            answer_span.set_attribute(
                "rag.context.length",
                len(context),
            )
            answer_span.set_status(
                Status(StatusCode.OK)
            )

            return {
                "question": question,
                "answer": answer,
                "sources": [
                    {
                        "document_name": row["document_name"],
                        "chunk_index": row["chunk_index"],
                        "content": row["content"],
                        "distance": float(row["distance"]),
                    }
                    for row in chunks
                ],
                "metadata": {
                    "model": MODEL_NAME,
                    "provider": PROVIDER_NAME,
                    "retrieval_count": len(chunks),
                    "generation_latency_ms": latency_ms,
                    "grounded": grounded,
                },
            }

        except Exception as exc:
            answer_span.record_exception(exc)
            answer_span.set_status(
                Status(
                    StatusCode.ERROR,
                    str(exc),
                )
            )
            raise