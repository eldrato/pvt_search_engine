import os
import re
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from app.models.document import Document, DocumentChunk
from app.core.config import settings
from app.core.logging import logger


class DocumentIntelligenceService:
    """
    Document Intelligence Service providing:
    - Exact location tracking (pages, paragraphs, code lines, bounding boxes)
    - Surrounding context navigation
    - Dynamic inline PDF rendering with visual highlights
    - Downloadable annotated PDFs with standard PDF highlights
    - Original file streaming
    """

    async def get_document_file(
        self,
        doc_id: str,
        db: AsyncSession
    ) -> Tuple[Optional[str], Optional[bytes], str, str]:
        """
        Retrieves the original file for a document.
        Returns: (file_path_on_disk, file_bytes, filename, mime_type)
        """
        stmt = select(Document).where(Document.id == doc_id)
        res = await db.execute(stmt)
        doc = res.scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        meta = doc.doc_metadata or {}
        filename = meta.get("original_filename") or (os.path.basename(doc.file_path) if doc.file_path else f"{doc.title}.txt")
        mime_type = doc.mime_type or "application/octet-stream"

        # Check if file_path exists on disk
        if doc.file_path and os.path.isfile(doc.file_path):
            return doc.file_path, None, filename, mime_type

        # Check if stored in STORAGE_DIR by content_hash or doc_id
        if hasattr(doc, "content_hash") and doc.content_hash:
            for fname in os.listdir(settings.STORAGE_DIR) if os.path.exists(settings.STORAGE_DIR) else []:
                if fname.startswith(doc.content_hash[:16]):
                    candidate = os.path.join(settings.STORAGE_DIR, fname)
                    if os.path.isfile(candidate):
                        return candidate, None, filename, mime_type

        # Fallback to raw_content in DB
        if doc.raw_content:
            return None, doc.raw_content.encode("utf-8"), filename, mime_type

        raise HTTPException(status_code=404, detail="Original document file not found on disk or storage")

    async def render_pdf_page(
        self,
        doc_id: str,
        page_number: int,
        highlight_query: Optional[str] = None,
        highlight_chunk_index: Optional[int] = None,
        db: Optional[AsyncSession] = None
    ) -> bytes:
        """
        Renders a specific page of a PDF as a high-resolution PNG image with optional
        visual highlights over matching text or chunk bounding boxes.
        """
        import pymupdf

        if not db:
            raise HTTPException(status_code=500, detail="Database session required")

        file_path, file_bytes, filename, mime_type = await self.get_document_file(doc_id, db)

        try:
            if file_path:
                doc = pymupdf.open(file_path)
            elif file_bytes:
                doc = pymupdf.open(stream=file_bytes, filetype="pdf")
            else:
                raise HTTPException(status_code=404, detail="Cannot access PDF content")
        except Exception as err:
            logger.error(f"Failed to open PDF document {doc_id}: {err}")
            raise HTTPException(status_code=400, detail=f"Failed to open PDF: {str(err)}")

        total_pages = len(doc)
        if page_number < 1 or page_number > total_pages:
            doc.close()
            raise HTTPException(
                status_code=400,
                detail=f"Invalid page number {page_number}. Document has {total_pages} pages."
            )

        page = doc[page_number - 1]

        # 1. Apply highlights from specific chunk if requested
        if highlight_chunk_index is not None and db:
            c_stmt = (
                select(DocumentChunk)
                .where(
                    DocumentChunk.document_id == doc_id,
                    DocumentChunk.chunk_index == highlight_chunk_index
                )
            )
            c_res = await db.execute(c_stmt)
            chunk = c_res.scalar_one_or_none()

            if chunk and chunk.location_meta:
                meta = chunk.location_meta
                # Bounding boxes
                bboxes = meta.get("bboxes", [])
                for b in bboxes:
                    if len(b) >= 4:
                        try:
                            rect = pymupdf.Rect(b[0], b[1], b[2], b[3])
                            # Only apply if rect overlaps with current page
                            if 0 <= rect.x0 <= page.rect.width and 0 <= rect.y0 <= page.rect.height:
                                annot = page.add_highlight_annot(rect)
                                if annot:
                                    annot.set_colors(stroke=(1.0, 0.85, 0.2))  # Warm amber/yellow
                                    annot.update()
                        except Exception:
                            pass

                # If no bounding boxes or in addition, search for distinct text phrases from chunk
                if not bboxes and chunk.content:
                    lines = [ln.strip() for ln in chunk.content.splitlines() if len(ln.strip()) > 8]
                    for line in lines[:5]:
                        try:
                            rects = page.search_for(line[:80])
                            for r in rects:
                                annot = page.add_highlight_annot(r)
                                if annot:
                                    annot.set_colors(stroke=(1.0, 0.85, 0.2))
                                    annot.update()
                        except Exception:
                            pass

        # 2. Apply query term highlights if provided
        if highlight_query:
            terms = [t for t in re.findall(r"\w+", highlight_query) if len(t) > 1]
            # Also search full phrase if multiple words
            search_targets = [highlight_query.strip()] if len(terms) > 1 else []
            search_targets.extend(terms)

            for target in search_targets[:8]:
                try:
                    rects = page.search_for(target)
                    for r in rects:
                        annot = page.add_highlight_annot(r)
                        if annot:
                            annot.set_colors(stroke=(1.0, 0.9, 0.0))  # Vivid yellow
                            annot.update()
                except Exception:
                    pass

        # Render page to PNG pixmap
        try:
            pix = page.get_pixmap(dpi=150)
            png_bytes = pix.tobytes("png")
        finally:
            doc.close()

        return png_bytes

    async def get_annotated_pdf(
        self,
        doc_id: str,
        highlight_query: Optional[str] = None,
        highlight_chunk_index: Optional[int] = None,
        db: Optional[AsyncSession] = None
    ) -> bytes:
        """
        Returns a complete PDF binary with standard PDF highlight annotations applied
        to all matching pages.
        """
        import pymupdf

        if not db:
            raise HTTPException(status_code=500, detail="Database session required")

        file_path, file_bytes, filename, mime_type = await self.get_document_file(doc_id, db)

        try:
            if file_path:
                doc = pymupdf.open(file_path)
            elif file_bytes:
                doc = pymupdf.open(stream=file_bytes, filetype="pdf")
            else:
                raise HTTPException(status_code=404, detail="Cannot access PDF content")
        except Exception as err:
            raise HTTPException(status_code=400, detail=f"Failed to open PDF: {str(err)}")

        # Gather target chunk data if requested
        chunk_bboxes = []
        chunk_lines = []
        if highlight_chunk_index is not None:
            c_stmt = (
                select(DocumentChunk)
                .where(
                    DocumentChunk.document_id == doc_id,
                    DocumentChunk.chunk_index == highlight_chunk_index
                )
            )
            c_res = await db.execute(c_stmt)
            chunk = c_res.scalar_one_or_none()
            if chunk and chunk.location_meta:
                chunk_bboxes = chunk.location_meta.get("bboxes", [])
                if chunk.content:
                    chunk_lines = [ln.strip() for ln in chunk.content.splitlines() if len(ln.strip()) > 8]

        query_terms = [t for t in re.findall(r"\w+", highlight_query) if len(t) > 1] if highlight_query else []

        # Annotate across pages
        for page_idx in range(len(doc)):
            page = doc[page_idx]

            # Bboxes on this page
            for b in chunk_bboxes:
                if len(b) >= 4:
                    try:
                        rect = pymupdf.Rect(b[0], b[1], b[2], b[3])
                        annot = page.add_highlight_annot(rect)
                        if annot:
                            annot.set_colors(stroke=(1.0, 0.85, 0.2))
                            annot.update()
                    except Exception:
                        pass

            # Chunk lines search
            for line in chunk_lines[:4]:
                try:
                    rects = page.search_for(line[:80])
                    for r in rects:
                        annot = page.add_highlight_annot(r)
                        if annot:
                            annot.set_colors(stroke=(1.0, 0.85, 0.2))
                            annot.update()
                except Exception:
                    pass

            # Query term matches
            for term in query_terms:
                try:
                    rects = page.search_for(term)
                    for r in rects:
                        annot = page.add_highlight_annot(r)
                        if annot:
                            annot.set_colors(stroke=(1.0, 0.9, 0.0))
                            annot.update()
                except Exception:
                    pass

        try:
            pdf_bytes = doc.tobytes()
        finally:
            doc.close()

        return pdf_bytes

    async def get_document_locations(
        self,
        doc_id: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Returns full structural map of all chunks, anchors, and pages in a document.
        """
        stmt = select(Document).where(Document.id == doc_id)
        res = await db.execute(stmt)
        doc = res.scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        c_stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == doc_id)
            .order_by(DocumentChunk.chunk_index)
        )
        c_res = await db.execute(c_stmt)
        chunks = c_res.scalars().all()

        meta = doc.doc_metadata or {}
        is_pdf = doc.mime_type == "application/pdf" or (doc.file_path and doc.file_path.endswith(".pdf"))

        chunks_data = []
        for c in chunks:
            loc = c.location_meta or {}
            anchor = loc.get("anchor_label") or f"Chunk #{c.chunk_index + 1}"
            chunks_data.append({
                "chunk_id": c.id,
                "chunk_index": c.chunk_index,
                "token_count": c.token_count,
                "anchor_label": anchor,
                "location_meta": loc,
                "snippet": c.content[:220] + ("..." if len(c.content) > 220 else "")
            })

        return {
            "document_id": doc.id,
            "title": doc.title,
            "source_type": doc.source_type,
            "mime_type": doc.mime_type,
            "file_path": doc.file_path,
            "is_pdf": is_pdf,
            "total_pages": meta.get("total_pages", 1 if is_pdf else 0),
            "total_paragraphs": meta.get("total_paragraphs", len(chunks)),
            "total_lines": meta.get("total_lines", 0),
            "total_chunks": len(chunks),
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "chunks": chunks_data
        }

    async def get_chunk_location_context(
        self,
        doc_id: str,
        chunk_index: int,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Returns granular location intelligence for a specific chunk, including
        preceding and succeeding chunks for reading context.
        """
        stmt = select(Document).where(Document.id == doc_id)
        res = await db.execute(stmt)
        doc = res.scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Fetch target chunk
        c_stmt = (
            select(DocumentChunk)
            .where(
                DocumentChunk.document_id == doc_id,
                DocumentChunk.chunk_index == chunk_index
            )
        )
        c_res = await db.execute(c_stmt)
        target = c_res.scalar_one_or_none()
        if not target:
            raise HTTPException(status_code=404, detail=f"Chunk {chunk_index} not found for document {doc_id}")

        # Fetch previous chunk
        prev_chunk = None
        if chunk_index > 0:
            p_stmt = (
                select(DocumentChunk)
                .where(
                    DocumentChunk.document_id == doc_id,
                    DocumentChunk.chunk_index == chunk_index - 1
                )
            )
            p_res = await db.execute(p_stmt)
            prev_chunk = p_res.scalar_one_or_none()

        # Fetch next chunk
        next_chunk = None
        n_stmt = (
            select(DocumentChunk)
            .where(
                DocumentChunk.document_id == doc_id,
                DocumentChunk.chunk_index == chunk_index + 1
            )
        )
        n_res = await db.execute(n_stmt)
        next_chunk = n_res.scalar_one_or_none()

        loc_meta = target.location_meta or {}
        anchor_label = loc_meta.get("anchor_label", f"Chunk #{target.chunk_index + 1}")
        is_pdf = doc.mime_type == "application/pdf" or (doc.file_path and doc.file_path.endswith(".pdf"))
        meta = doc.doc_metadata or {}

        return {
            "document_id": doc.id,
            "title": doc.title,
            "source_type": doc.source_type,
            "mime_type": doc.mime_type,
            "file_path": doc.file_path,
            "is_pdf": is_pdf,
            "total_pages": meta.get("total_pages", 1 if is_pdf else 0),
            "chunk": {
                "id": target.id,
                "chunk_index": target.chunk_index,
                "content": target.content,
                "token_count": target.token_count,
                "anchor_label": anchor_label,
                "location_meta": loc_meta,
            },
            "previous_chunk": {
                "id": prev_chunk.id,
                "chunk_index": prev_chunk.chunk_index,
                "content": prev_chunk.content,
                "anchor_label": (prev_chunk.location_meta or {}).get("anchor_label", f"Chunk #{prev_chunk.chunk_index + 1}"),
                "location_meta": prev_chunk.location_meta or {}
            } if prev_chunk else None,
            "next_chunk": {
                "id": next_chunk.id,
                "chunk_index": next_chunk.chunk_index,
                "content": next_chunk.content,
                "anchor_label": (next_chunk.location_meta or {}).get("anchor_label", f"Chunk #{next_chunk.chunk_index + 1}"),
                "location_meta": next_chunk.location_meta or {}
            } if next_chunk else None,
        }


document_intelligence_service = DocumentIntelligenceService()
