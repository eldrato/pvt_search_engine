import hashlib
import os
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.document import Document, DocumentChunk
from app.ingestion.parsers import get_parser, ParsedDocument
from app.ingestion.chunker import Chunker, Chunk
from app.services.opensearch import opensearch_service
from app.services.embedding import embedding_service
from app.services.qdrant import qdrant_service
from app.core.logging import logger


class IngestionService:
    def __init__(self):
        self.chunker = Chunker(target_chars=1500, overlap_chars=200)

    async def ingest_file(
        self,
        content: bytes,
        filename: str,
        mime_type: Optional[str] = None,
        source_type: str = "upload",
        doc_metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        content_hash = hashlib.sha256(content).hexdigest()
        file_size = len(content)

        # 1. Check for existing document by hash
        if db:
            stmt = select(Document).where(Document.content_hash == content_hash)
            res = await db.execute(stmt)
            existing = res.scalar_one_or_none()
            if existing:
                logger.info(f"Document '{filename}' already ingested (id: {existing.id})")
                return {
                    "document": existing.to_dict(),
                    "chunks_created": 0,
                    "is_duplicate": True,
                    "message": "Document already ingested"
                }

        # 2. Parse document format
        parser = get_parser(filename=filename, mime_type=mime_type)
        parsed_doc: ParsedDocument = parser.parse(content=content, filename=filename)

        # 3. Generate structural chunks
        chunks: List[Chunk] = self.chunker.chunk_document(parsed_doc)

        # 4. Save to SSOT Database
        combined_meta = {**(doc_metadata or {}), **parsed_doc.metadata}

        doc = Document(
            title=parsed_doc.title,
            source_type=source_type,
            file_path=filename,
            mime_type=parsed_doc.mime_type,
            file_size_bytes=file_size,
            content_hash=content_hash,
            raw_content=parsed_doc.raw_text[:100000],  # Store up to 100k chars
            doc_metadata=combined_meta
        )

        if db:
            db.add(doc)
            await db.flush()  # populate doc.id

            db_chunks = []
            for c in chunks:
                db_chunk = DocumentChunk(
                    document_id=doc.id,
                    chunk_index=c.chunk_index,
                    content=c.content,
                    token_count=c.token_count,
                    chunk_hash=c.chunk_hash,
                    location_meta=c.location_meta
                )
                db_chunks.append(db_chunk)
                db.add(db_chunk)

            await db.commit()
            await db.refresh(doc)
            doc_id = doc.id
        else:
            doc_id = "mem_" + content_hash[:8]

        # 5. Index into OpenSearch (Derived BM25 Index)
        opensearch_payloads = []
        for c in chunks:
            payload = {
                "chunk_id": f"{doc_id}_{c.chunk_index}",
                "document_id": doc_id,
                "title": parsed_doc.title,
                "content": c.content,
                "source_type": source_type,
                "mime_type": parsed_doc.mime_type,
                "anchor_label": c.anchor_label,
                "chunk_index": c.chunk_index,
                "token_count": c.token_count,
                "location_meta": c.location_meta,
                "created_at": doc.created_at.isoformat() if hasattr(doc, "created_at") and doc.created_at else None
            }
            opensearch_payloads.append(payload)

        if opensearch_service.is_connected():
            indexed_count = opensearch_service.bulk_index_chunks(opensearch_payloads)
            logger.info(f"Indexed {indexed_count} chunks in OpenSearch for document {doc_id}")

        # 6. Index into Qdrant (Derived Dense Vector Index)
        try:
            if qdrant_service.is_connected() and chunks:
                chunk_texts = [c.content for c in chunks]
                vectors = embedding_service.embed_documents(chunk_texts)
                qdrant_indexed = qdrant_service.upsert_chunks(opensearch_payloads, vectors)
                logger.info(f"Indexed {qdrant_indexed} vectors in Qdrant for document {doc_id}")
        except Exception as q_err:
            logger.warning(f"Failed to index vectors in Qdrant for document {doc_id}: {q_err}")

        return {
            "document": doc.to_dict() if hasattr(doc, "to_dict") else {"id": doc_id, "title": parsed_doc.title},
            "chunks_created": len(chunks),
            "is_duplicate": False,
            "message": f"Successfully ingested '{parsed_doc.title}' with {len(chunks)} chunks"
        }

    async def ingest_text(
        self,
        title: str,
        text: str,
        source_type: str = "note",
        doc_metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        content_bytes = text.encode("utf-8")
        filename = f"{title.lower().replace(' ', '_')}.txt"
        return await self.ingest_file(
            content=content_bytes,
            filename=filename,
            mime_type="text/plain",
            source_type=source_type,
            doc_metadata=doc_metadata,
            db=db
        )

    async def ingest_url(
        self,
        url: str,
        custom_title: Optional[str] = None,
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        import httpx
        import urllib.parse

        url = url.strip()
        parsed = urllib.parse.urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid URL: {url}")

        domain = parsed.netloc.replace("www.", "")
        headers = {
            "User-Agent": "AegisSearchBot/1.0 (https://aegis.local; contact@aegis.local)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"Failed to fetch webpage: HTTP {resp.status_code}")
            content_bytes = resp.content

        filename = custom_title or parsed.path.split("/")[-1] or domain
        if not filename.endswith(".html"):
            filename = f"{filename}.html"

        return await self.ingest_file(
            content=content_bytes,
            filename=filename,
            mime_type="text/html",
            source_type="web",
            doc_metadata={"url": url, "domain": domain, "ingested_from": "web"},
            db=db
        )


ingestion_service = IngestionService()
