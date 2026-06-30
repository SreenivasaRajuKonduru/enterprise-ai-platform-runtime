from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.rag.embedder import generate_embedding


def retrieve_relevant_chunks(db: Session, query: str, limit: int = 3):
    query_embedding = generate_embedding(query)
    query_embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

    results = db.execute(
        text("""
            SELECT
                document_name,
                chunk_index,
                content,
                embedding <-> CAST(:query_embedding AS vector) AS distance
            FROM document_chunks
            ORDER BY embedding <-> CAST(:query_embedding AS vector)
            LIMIT :limit
        """),
        {
            "query_embedding": query_embedding_str,
            "limit": limit,
        },
    ).mappings().all()

    return results