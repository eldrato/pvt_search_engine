from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.source import SourceConfig
from app.models.document import Document, DocumentChunk
from app.core.logging import logger


class SourceManagerService:
    """
    Manages personal knowledge sources and per-source indexing toggles (Phase 6).
    """

    async def list_sources(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """
        List all registered sources with real-time document count, chunk count,
        and enabled status.
        """
        stmt = select(SourceConfig).order_by(SourceConfig.display_name)
        res = await db.execute(stmt)
        sources = res.scalars().all()

        # Gather document and chunk statistics per source
        doc_stats_stmt = (
            select(
                Document.source_type,
                func.count(Document.id).label("doc_count")
            )
            .group_by(Document.source_type)
        )
        doc_res = await db.execute(doc_stats_stmt)
        doc_counts = {row.source_type: row.doc_count for row in doc_res.all()}

        chunk_stats_stmt = (
            select(
                Document.source_type,
                func.count(DocumentChunk.id).label("chunk_count")
            )
            .join(DocumentChunk, DocumentChunk.document_id == Document.id)
            .group_by(Document.source_type)
        )
        chunk_res = await db.execute(chunk_stats_stmt)
        chunk_counts = {row.source_type: row.chunk_count for row in chunk_res.all()}

        result = []
        for s in sources:
            d = s.to_dict()
            d["document_count"] = doc_counts.get(s.source_type, 0)
            d["chunk_count"] = chunk_counts.get(s.source_type, 0)
            result.append(d)

        return result

    async def get_enabled_source_types(self, db: Optional[AsyncSession] = None) -> List[str]:
        """
        Returns list of source types that are currently enabled for search and retrieval.
        Falls back to all known types if DB session is unavailable.
        """
        default_types = ["upload", "note", "code", "web"]
        if not db:
            return default_types

        try:
            stmt = select(SourceConfig.source_type).where(SourceConfig.enabled == True)
            res = await db.execute(stmt)
            enabled = [row[0] for row in res.all()]
            return enabled if enabled else default_types
        except Exception as e:
            logger.warning(f"Error querying enabled sources: {e}. Defaulting to all.")
            return default_types

    async def update_source(
        self,
        db: AsyncSession,
        source_type: str,
        enabled: Optional[bool] = None,
        default_privacy_tier: Optional[str] = None,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Updates source configuration (enable/disable or change default privacy tier).
        """
        stmt = select(SourceConfig).where(SourceConfig.source_type == source_type)
        res = await db.execute(stmt)
        source = res.scalar_one_or_none()

        if not source:
            return None

        if enabled is not None:
            source.enabled = enabled
        if default_privacy_tier is not None:
            valid_tiers = {"public", "private", "sensitive"}
            if default_privacy_tier.lower() in valid_tiers:
                source.default_privacy_tier = default_privacy_tier.lower()
        if display_name is not None:
            source.display_name = display_name
        if description is not None:
            source.description = description

        source.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(source)
        logger.info(f"Updated source '{source_type}' (enabled={source.enabled}, tier={source.default_privacy_tier})")
        return source.to_dict()

    async def toggle_source(self, db: AsyncSession, source_type: str, enabled: bool) -> Optional[Dict[str, Any]]:
        return await self.update_source(db=db, source_type=source_type, enabled=enabled)

    async def get_default_tier_for_source(self, db: Optional[AsyncSession], source_type: str) -> str:
        """
        Returns the configured default privacy tier for a source type.
        """
        if not db:
            return "public" if source_type == "web" else "private"

        try:
            stmt = select(SourceConfig.default_privacy_tier).where(SourceConfig.source_type == source_type)
            res = await db.execute(stmt)
            tier = res.scalar_one_or_none()
            return tier or ("public" if source_type == "web" else "private")
        except Exception:
            return "public" if source_type == "web" else "private"


source_manager = SourceManagerService()
