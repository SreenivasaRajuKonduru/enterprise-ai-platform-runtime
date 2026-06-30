from sqlalchemy.orm import Session

from backend.app.rag.chunker import chunk_text
from backend.app.rag.embedder import generate_embedding
from backend.app.rag.models import DocumentChunk


def ingest_document(
    db: Session,
    document_name: str,
    content: str,
) -> int:
    chunks = chunk_text(content)

    saved_count = 0

    for index, chunk in enumerate(chunks):
        embedding = generate_embedding(chunk)

        db_chunk = DocumentChunk(
            document_name=document_name,
            chunk_index=index,
            content=chunk,
            embedding=embedding,
        )

        db.add(db_chunk)
        saved_count += 1

    db.commit()
    return saved_count