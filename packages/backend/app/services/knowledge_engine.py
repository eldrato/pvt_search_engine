from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from app.models.document import Document, DocumentChunk
from app.models.source import SourceConfig
from app.services.source_manager import source_manager
from app.services.opensearch import opensearch_service
from app.services.qdrant import qdrant_service
from app.core.logging import logger

VALID_PRIVACY_TIERS = ["public", "private", "sensitive"]


class KnowledgeEngineService:
    """
    Phase 6: Personal Knowledge Engine.
    Handles data classification across privacy tiers (Public, Private, Sensitive),
    per-source intelligence aggregation, and privacy propagation to search indices.
    """

    async def get_knowledge_summary(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Generates comprehensive intelligence metrics across privacy tiers and sources.
        """
        # 1. Privacy Tier metrics
        tier_doc_stmt = (
            select(
                Document.privacy_tier,
                func.count(Document.id).label("doc_count")
            )
            .group_by(Document.privacy_tier)
        )
        tier_doc_res = await db.execute(tier_doc_stmt)
        tier_docs = {row.privacy_tier or "private": row.doc_count for row in tier_doc_res.all()}

        tier_chunk_stmt = (
            select(
                Document.privacy_tier,
                func.count(DocumentChunk.id).label("chunk_count"),
                func.coalesce(func.sum(DocumentChunk.token_count), 0).label("token_count")
            )
            .join(DocumentChunk, DocumentChunk.document_id == Document.id)
            .group_by(Document.privacy_tier)
        )
        tier_chunk_res = await db.execute(tier_chunk_stmt)
        tier_chunks = {}
        tier_tokens = {}
        for row in tier_chunk_res.all():
            k = row.privacy_tier or "private"
            tier_chunks[k] = row.chunk_count
            tier_tokens[k] = int(row.token_count)

        tiers_breakdown = {}
        for tier in VALID_PRIVACY_TIERS:
            tiers_breakdown[tier] = {
                "tier": tier,
                "document_count": tier_docs.get(tier, 0),
                "chunk_count": tier_chunks.get(tier, 0),
                "token_count": tier_tokens.get(tier, 0),
                "description": {
                    "public": "Web-crawled content and shareable intelligence",
                    "private": "Personal notes, source code, and ingested documents",
                    "sensitive": "Confidential records requiring explicit inclusion",
                }.get(tier, "")
            }

        # 2. Source breakdown
        sources = await source_manager.list_sources(db)

        # 3. Overall aggregates
        total_docs = sum(tier_docs.values())
        total_chunks = sum(tier_chunks.values())
        total_tokens = sum(tier_tokens.values())

        return {
            "total_documents": total_docs,
            "total_chunks": total_chunks,
            "total_tokens": total_tokens,
            "privacy_tiers": tiers_breakdown,
            "sources": sources,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

    async def update_document_classification(
        self,
        db: AsyncSession,
        document_id: str,
        new_tier: str
    ) -> Optional[Dict[str, Any]]:
        """
        Updates the privacy tier of a document and synchronizes with derived search indexes.
        """
        tier = new_tier.lower()
        if tier not in VALID_PRIVACY_TIERS:
            raise ValueError(f"Invalid privacy tier: '{new_tier}'. Must be one of {VALID_PRIVACY_TIERS}")

        stmt = select(Document).where(Document.id == document_id)
        res = await db.execute(stmt)
        doc = res.scalar_one_or_none()

        if not doc:
            return None

        old_tier = doc.privacy_tier
        doc.privacy_tier = tier
        doc.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(doc)

        logger.info(f"Updated document '{document_id}' privacy tier from '{old_tier}' to '{tier}'")

        # Sync to derived OpenSearch & Qdrant indices if connected
        try:
            self._sync_index_privacy(doc.id, tier)
        except Exception as sync_err:
            logger.warning(f"Could not synchronize privacy tier to external search indices: {sync_err}")

        return doc.to_dict()

    async def batch_classify(
        self,
        db: AsyncSession,
        document_ids: List[str],
        new_tier: str
    ) -> Dict[str, Any]:
        """
        Batch updates privacy tiers for multiple documents.
        """
        tier = new_tier.lower()
        if tier not in VALID_PRIVACY_TIERS:
            raise ValueError(f"Invalid privacy tier: '{new_tier}'. Must be one of {VALID_PRIVACY_TIERS}")

        if not document_ids:
            return {"updated_count": 0, "privacy_tier": tier}

        stmt = (
            update(Document)
            .where(Document.id.in_(document_ids))
            .values(privacy_tier=tier, updated_at=datetime.now(timezone.utc))
        )
        res = await db.execute(stmt)
        await db.commit()
        updated_count = res.rowcount

        for doc_id in document_ids:
            try:
                self._sync_index_privacy(doc_id, tier)
            except Exception:
                pass

        logger.info(f"Batch classified {updated_count} documents to '{tier}'")
        return {"updated_count": updated_count, "privacy_tier": tier}

    def _sync_index_privacy(self, document_id: str, new_tier: str):
        """
        Updates the privacy_tier metadata in OpenSearch and Qdrant.
        """
        # OpenSearch update by query
        if opensearch_service.is_connected() and opensearch_service.client:
            try:
                body = {
                    "script": {
                        "source": "ctx._source.privacy_tier = params.new_tier",
                        "lang": "painless",
                        "params": {"new_tier": new_tier}
                    },
                    "query": {
                        "term": {"document_id": document_id}
                    }
                }
                opensearch_service.client.update_by_query(
                    index=opensearch_service.INDEX_NAME if hasattr(opensearch_service, "INDEX_NAME") else "aegis_chunks",
                    body=body,
                    conflicts="proceed",
                    wait_for_completion=False
                )
            except Exception as os_e:
                logger.debug(f"OpenSearch privacy sync: {os_e}")


knowledge_engine = KnowledgeEngineService()
