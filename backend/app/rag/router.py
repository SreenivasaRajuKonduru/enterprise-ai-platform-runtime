from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.rag.ingestion import ingest_document
from backend.app.rag.retriever import retrieve_relevant_chunks
from backend.app.rag.answer_service import generate_rag_answer

router = APIRouter(prefix="/ai-runtime/documents", tags=["RAG Documents"])


class DocumentIngestRequest(BaseModel):
    document_name: str
    content: str


@router.post("/ingest")
def ingest_document_api(
    request: DocumentIngestRequest,
    db: Session = Depends(get_db),
):
    chunks_created = ingest_document(
        db=db,
        document_name=request.document_name,
        content=request.content,
    )

    return {
        "message": "Document ingested successfully",
        "document_name": request.document_name,
        "chunks_created": chunks_created,
    }

class RetrievalRequest(BaseModel):
    query: str
    limit: int = 3
    
@router.post("/retrieve")
def retrieve_documents_api(
    request: RetrievalRequest,
    db: Session = Depends(get_db),
):
    results = retrieve_relevant_chunks(
        db=db,
        query=request.query,
        limit=request.limit,
    )

    return {
        "query": request.query,
        "results": [
            {
                "document_name": row["document_name"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "distance": float(row["distance"]),
            }
            for row in results
        ],
    }

class RagQuestionRequest(BaseModel):
    question: str
    
@router.post("/ask")
def ask_rag_api(
    request: RagQuestionRequest,
    db: Session = Depends(get_db),
):
    return generate_rag_answer(
        db=db,
        question=request.question,
    )