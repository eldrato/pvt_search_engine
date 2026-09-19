#!/usr/bin/env python3
"""
Aegis Single-Source-of-Truth (SSOT) Reconstitution Script

Reconstitutes derived search indexes (OpenSearch BM25 and Qdrant Vector DB)
entirely from PostgreSQL/SQLite SSOT and raw files.
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

# Add backend to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "packages" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select
from app.core.db import get_sessionmaker, init_db
from app.models.document import Document, DocumentChunk
from app.services.opensearch import opensearch_service, INDEX_NAME
from app.services.embedding import embedding_service
from app.services.qdrant import qdrant_service


async def reindex_opensearch() -> int:
    print("[SSOT Reindex] Probing database for document chunks to index into OpenSearch...")
    if not opensearch_service.is_connected():
        print("[SSOT Reindex] Warning: OpenSearch is not currently reachable. Skipping OpenSearch push.")
        return 0

    sm = get_sessionmaker()
    total_indexed = 0

    async with sm() as session:
        stmt = select(DocumentChunk, Document).join(Document, DocumentChunk.document_id == Document.id)
        res = await session.execute(stmt)
        rows = res.all()

        if not rows:
            print("[SSOT Reindex] No document chunks found in database.")
            return 0

        payloads = []
        for chunk, doc in rows:
            payloads.append({
                "chunk_id": f"{doc.id}_{chunk.chunk_index}",
                "document_id": doc.id,
                "title": doc.title,
                "content": chunk.content,
                "source_type": doc.source_type,
                "mime_type": doc.mime_type,
                "anchor_label": chunk.location_meta.get("anchor_label", f"Chunk #{chunk.chunk_index + 1}"),
                "chunk_index": chunk.chunk_index,
                "token_count": chunk.token_count,
                "location_meta": chunk.location_meta,
                "created_at": doc.created_at.isoformat() if doc.created_at else None
            })

        total_indexed = opensearch_service.bulk_index_chunks(payloads)
        print(f"[SSOT Reindex] Successfully streamed {total_indexed} chunks into OpenSearch '{INDEX_NAME}'.")

    return total_indexed


async def reindex_qdrant() -> int:
    print("[SSOT Reindex] Probing database for document chunks to embed into Qdrant...")
    if not qdrant_service.is_connected():
        print("[SSOT Reindex] Warning: Qdrant service is unavailable.")
        return 0

    sm = get_sessionmaker()
    total_indexed = 0

    async with sm() as session:
        stmt = select(DocumentChunk, Document).join(Document, DocumentChunk.document_id == Document.id)
        res = await session.execute(stmt)
        rows = res.all()

        if not rows:
            print("[SSOT Reindex] No document chunks found in database to embed.")
            return 0

        print(f"[SSOT Reindex] Found {len(rows)} chunks. Computing local embeddings (model: {embedding_service.model_name})...")
        payloads = []
        texts = []
        for chunk, doc in rows:
            payloads.append({
                "chunk_id": f"{doc.id}_{chunk.chunk_index}",
                "document_id": doc.id,
                "title": doc.title,
                "content": chunk.content,
                "source_type": doc.source_type,
                "mime_type": doc.mime_type,
                "anchor_label": chunk.location_meta.get("anchor_label", f"Chunk #{chunk.chunk_index + 1}"),
                "chunk_index": chunk.chunk_index,
                "token_count": chunk.token_count,
                "location_meta": chunk.location_meta,
                "created_at": doc.created_at.isoformat() if doc.created_at else None
            })
            texts.append(chunk.content)

        # Batch embedding in chunks of 32
        batch_size = 32
        all_vectors = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            vecs = embedding_service.embed_documents(batch_texts)
            all_vectors.extend(vecs)
            print(f"[SSOT Reindex] Embedded {len(all_vectors)}/{len(texts)} chunks...")

        total_indexed = qdrant_service.upsert_chunks(payloads, all_vectors)
        mode_desc = "local fallback storage" if qdrant_service.is_local_fallback() else "remote Qdrant server"
        print(f"[SSOT Reindex] Successfully indexed {total_indexed} dense vectors into Qdrant '{qdrant_service.collection_name}' ({mode_desc}).")

    return total_indexed


async def main():
    parser = argparse.ArgumentParser(description="Reconstitute derived search indexes from SSOT.")
    parser.add_argument("--target", choices=["all", "opensearch", "qdrant"], default="all", help="Target index to reconstitute")
    args = parser.parse_args()

    start_time = time.time()
    print(f"=== Aegis SSOT Reindex Engine [Target: {args.target}] ===")

    await init_db()

    if args.target in ["all", "opensearch"]:
        await reindex_opensearch()
    if args.target in ["all", "qdrant"]:
        await reindex_qdrant()

    elapsed = time.time() - start_time
    print(f"=== Reconstitution completed in {elapsed:.2f}s ===")


if __name__ == "__main__":
    asyncio.run(main())
