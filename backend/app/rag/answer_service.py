import re
from time import perf_counter

from sqlalchemy.orm import Session

from backend.app.rag.retriever import retrieve_relevant_chunks
from backend.app.llm.ollama_client import generate_answer



def generate_rag_answer(db: Session, question: str):
    chunks = retrieve_relevant_chunks(
        db=db,
        query=question,
        limit=3,
    )

    context = "\n\n".join(
        [row["content"] for row in chunks]
    )

    if not context:
        return {
            "question": question,
            "answer": "The provided context does not contain enough information.",
            "sources": [],
            "metadata": {
                "model": "llama3.2",
                "provider": "ollama",
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
            "Retrieval-Augmented Generation (RAG) memory",
            answer,
        )

        grounded = True
    except Exception:
        answer = (
            "LLM generation failed. Returning retrieved context instead:\n\n"
            f"{context}"
        )
        grounded = False

    latency_ms = round((perf_counter() - start_time) * 1000, 2)

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
            "model": "llama3.2",
            "provider": "ollama",
            "retrieval_count": len(chunks),
            "generation_latency_ms": latency_ms,
            "grounded": grounded,
        },
    }