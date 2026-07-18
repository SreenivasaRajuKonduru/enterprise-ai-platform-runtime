from time import perf_counter

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.rag.embedder import generate_embedding

tracer = trace.get_tracer(__name__)


def retrieve_relevant_chunks(
    db: Session,
    query: str,
    limit: int = 3,
):
    with tracer.start_as_current_span(
        "rag.retrieve",
        attributes={
            "rag.vector_store": "pgvector",
            "rag.retrieval.limit": limit,
            "rag.query.length": len(query),
        },
    ) as span:
        start_time = perf_counter()

        try:
            query_embedding = generate_embedding(query)

            span.set_attribute(
                "rag.embedding.dimensions",
                len(query_embedding),
            )

            query_embedding_str = (
                "["
                + ",".join(map(str, query_embedding))
                + "]"
            )

            results = db.execute(
                text("""
                    SELECT
                        document_name,
                        chunk_index,
                        content,
                        embedding <-> CAST(
                            :query_embedding AS vector
                        ) AS distance
                    FROM document_chunks
                    ORDER BY embedding <-> CAST(
                        :query_embedding AS vector
                    )
                    LIMIT :limit
                """),
                {
                    "query_embedding": query_embedding_str,
                    "limit": limit,
                },
            ).mappings().all()

            latency_ms = round(
                (perf_counter() - start_time) * 1000,
                2,
            )

            span.set_attribute(
                "rag.retrieval.count",
                len(results),
            )
            span.set_attribute(
                "rag.retrieval.latency_ms",
                latency_ms,
            )

            if results:
                span.set_attribute(
                    "rag.retrieval.best_distance",
                    float(results[0]["distance"]),
                )

            span.set_status(
                Status(StatusCode.OK)
            )

            return results

        except Exception as exc:
            span.record_exception(exc)
            span.set_status(
                Status(
                    StatusCode.ERROR,
                    str(exc),
                )
            )
            raise