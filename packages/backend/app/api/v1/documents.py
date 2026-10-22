import os
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.core.db import get_async_session
from app.models.document import Document, DocumentChunk
from app.services.ingestion import ingestion_service
from app.services.opensearch import opensearch_service
from app.services.document_intelligence import document_intelligence_service
from app.services.knowledge_engine import knowledge_engine
from app.core.logging import logger

router = APIRouter(prefix="/documents", tags=["Documents"])


class IngestTextRequest(BaseModel):
    title: str = Field(..., description="Document or note title")
    content: str = Field(..., description="Raw text or note content")
    source_type: str = Field(default="note", description="Source category: note, code, or personal")
    privacy_tier: Optional[str] = Field(None, description="Privacy tier: public, private, or sensitive")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata tags")


class DocumentSummary(BaseModel):
    id: str
    title: str
    source_type: str
    privacy_tier: str = "private"
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


class UpdateClassificationRequest(BaseModel):
    privacy_tier: str = Field(..., pattern="^(public|private|sensitive)$", description="Target privacy tier")


class BatchClassifyRequest(BaseModel):
    document_ids: List[str] = Field(..., min_length=1, description="List of document IDs to reclassify")
    privacy_tier: str = Field(..., pattern="^(public|private|sensitive)$", description="Target privacy tier")


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    source_type: str = Form("upload"),
    privacy_tier: Optional[str] = Form(None),
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
            privacy_tier=privacy_tier,
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
            privacy_tier=req.privacy_tier,
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

    # Clean up file on disk if exists
    if doc.file_path and os.path.isfile(doc.file_path):
        try:
            os.remove(doc.file_path)
        except Exception:
            pass

    # Delete from DB (cascade deletes DocumentChunk)
    await db.delete(doc)
    await db.commit()

    return {"message": f"Document '{doc.title}' deleted successfully", "id": doc_id}


@router.get("/{doc_id}/file")
async def get_raw_document_file(
    doc_id: str,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Stream or download the original raw document file (PDF, code, docx, markdown, text).
    Supports browser inline viewing (e.g. native PDF viewer).
    """
    file_path, file_bytes, filename, mime_type = await document_intelligence_service.get_document_file(doc_id, db)

    if file_path and os.path.isfile(file_path):
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type=mime_type,
            content_disposition_type="inline"
        )
    elif file_bytes:
        return Response(
            content=file_bytes,
            media_type=mime_type,
            headers={"Content-Disposition": f'inline; filename="{filename}"'}
        )
    else:
        raise HTTPException(status_code=404, detail="File content not found")


@router.get("/{doc_id}/pdf/page/{page_number}")
async def get_pdf_page_image(
    doc_id: str,
    page_number: int,
    highlight_query: Optional[str] = Query(None, description="Search terms to highlight visually on page"),
    highlight_chunk: Optional[int] = Query(None, description="Chunk index to highlight bounding boxes/text"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Render a specific page of a PDF document as a crisp PNG image with optional
    visual highlights (amber/yellow) over search query matches or chunk bounding boxes.
    """
    png_bytes = await document_intelligence_service.render_pdf_page(
        doc_id=doc_id,
        page_number=page_number,
        highlight_query=highlight_query,
        highlight_chunk_index=highlight_chunk,
        db=db
    )
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=60"}
    )


@router.get("/{doc_id}/pdf/highlighted")
async def get_highlighted_pdf(
    doc_id: str,
    highlight_query: Optional[str] = Query(None, description="Search query to highlight"),
    highlight_chunk: Optional[int] = Query(None, description="Specific chunk index to highlight"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Generate and stream a copy of the PDF document with standard PDF highlight annotations
    applied across all matching pages and chunks.
    """
    pdf_bytes = await document_intelligence_service.get_annotated_pdf(
        doc_id=doc_id,
        highlight_query=highlight_query,
        highlight_chunk_index=highlight_chunk,
        db=db
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="highlighted_{doc_id}.pdf"'}
    )


@router.get("/{doc_id}/locations")
async def get_document_locations(
    doc_id: str,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Retrieve structural map of document: total pages, paragraphs, lines, and all chunk anchors.
    """
    return await document_intelligence_service.get_document_locations(doc_id, db)


@router.get("/{doc_id}/location/{chunk_index}")
async def get_chunk_location_context(
    doc_id: str,
    chunk_index: int,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Retrieve exact location intelligence for a specific chunk, including previous and next chunk
    for surrounding reading context.
    """
    return await document_intelligence_service.get_chunk_location_context(doc_id, chunk_index, db)


@router.patch("/{doc_id}/classification")
async def update_document_classification(
    doc_id: str,
    payload: UpdateClassificationRequest,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update privacy classification tier of a document (public, private, sensitive)
    and propagate to search indices (Phase 6).
    """
    try:
        updated = await knowledge_engine.update_document_classification(
            db=db,
            document_id=doc_id,
            new_tier=payload.privacy_tier
        )
        if not updated:
            raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")
        return updated
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        logger.error(f"Error classifying document {doc_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update document classification: {str(e)}")


@router.post("/batch-classify")
async def batch_classify_documents(
    payload: BatchClassifyRequest,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Batch update privacy tiers for multiple documents (Phase 6).
    """
    try:
        return await knowledge_engine.batch_classify(
            db=db,
            document_ids=payload.document_ids,
            new_tier=payload.privacy_tier
        )
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        logger.error(f"Error in batch classification: {e}")
        raise HTTPException(status_code=500, detail=f"Batch classification failed: {str(e)}")

