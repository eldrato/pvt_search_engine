from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.core.db import get_async_session
from app.models.document import Document, DocumentChunk
from app.services.ingestion import ingestion_service
from app.services.opensearch import opensearch_service
from app.core.logging import logger

router = APIRouter(prefix="/documents", tags=["Documents"])


class IngestTextRequest(BaseModel):
    title: str = Field(..., description="Document or note title")
    content: str = Field(..., description="Raw text or note content")
    source_type: str = Field(default="note", description="Source category: note, code, or personal")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata tags")


class DocumentSummary(BaseModel):
    id: str
    title: str
    source_type: str
    file_path: Optional[str] = None
    mime_type: str
    file_size_bytes: int
    content_hash: str
    chunk_count: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DocumentListResponse(BaseModel):
    total: int
    documents: List[DocumentSummary]


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    source_type: str = Form("upload"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Ingest an uploaded document (PDF, DOCX, Markdown, Code, Plain Text).
    Extracts text, preserves structural anchors, saves to SSOT, and indexes to OpenSearch.
    """
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        res = await ingestion_service.ingest_file(
            content=content,
            filename=file.filename or "uploaded_file.txt",
            mime_type=file.content_type,
            source_type=source_type,
            db=db
        )
        return res
    except Exception as e:
        logger.error(f"Error ingesting file {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to ingest document: {str(e)}")


@router.post("/text", status_code=status.HTTP_201_CREATED)
async def ingest_raw_text(
    req: IngestTextRequest,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Directly ingest a markdown note, snippet, or text document.
    """
    try:
        res = await ingestion_service.ingest_text(
            title=req.title,
            text=req.content,
            source_type=req.source_type,
            doc_metadata=req.metadata,
            db=db
        )
        return res
    except Exception as e:
        logger.error(f"Error ingesting note '{req.title}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to ingest note: {str(e)}")


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    source_type: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session)
):
    """
    List all documents in the PostgreSQL Single Source of Truth (SSOT).
    """
    # Count total
    count_stmt = select(func.count(Document.id))
    if source_type:
        count_stmt = count_stmt.where(Document.source_type == source_type)
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    # Query items with chunk counts
    stmt = (
        select(Document, func.count(DocumentChunk.id).label("chunk_count"))
        .outerjoin(DocumentChunk, Document.id == DocumentChunk.document_id)
        .group_by(Document.id)
        .order_by(desc(Document.created_at))
        .offset(offset)
        .limit(limit)
    )
    if source_type:
        stmt = stmt.where(Document.source_type == source_type)

    res = await db.execute(stmt)
    rows = res.all()

    documents = []
    for doc, chunk_count in rows:
        documents.append(DocumentSummary(
            id=doc.id,
            title=doc.title,
            source_type=doc.source_type,
            file_path=doc.file_path,
            mime_type=doc.mime_type,
            file_size_bytes=doc.file_size_bytes,
            content_hash=doc.content_hash,
            chunk_count=chunk_count,
            created_at=doc.created_at.isoformat() if doc.created_at else None,
            updated_at=doc.updated_at.isoformat() if doc.updated_at else None,
        ))

    return DocumentListResponse(total=total, documents=documents)


@router.get("/{doc_id}")
async def get_document_details(
    doc_id: str,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Retrieve document metadata and all granular chunks with anchors.
    """
    stmt = select(Document).where(Document.id == doc_id)
    res = await db.execute(stmt)
    doc = res.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    chunk_stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == doc_id)
        .order_by(DocumentChunk.chunk_index)
    )
    c_res = await db.execute(chunk_stmt)
    chunks = [c.to_dict() for c in c_res.scalars().all()]

    data = doc.to_dict()
    data["chunks"] = chunks
    return data


@router.delete("/{doc_id}", status_code=status.HTTP_200_OK)
async def delete_document(
    doc_id: str,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Delete a document from SSOT and wipe its chunks from OpenSearch index.
    """
    stmt = select(Document).where(Document.id == doc_id)
    res = await db.execute(stmt)
    doc = res.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Wipe from OpenSearch
    opensearch_service.delete_document_chunks(doc_id)

    # Delete from DB (cascade deletes DocumentChunk)
    await db.delete(doc)
    await db.commit()

    return {"message": f"Document '{doc.title}' deleted successfully", "id": doc_id}
