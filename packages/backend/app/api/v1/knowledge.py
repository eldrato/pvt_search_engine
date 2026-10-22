from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_async_session
from app.services.knowledge_engine import knowledge_engine

router = APIRouter(prefix="/knowledge", tags=["Knowledge Engine"])


@router.get("/summary")
async def get_knowledge_summary(
    db: AsyncSession = Depends(get_async_session)
) -> Dict[str, Any]:
    """
    Get aggregated intelligence metrics across Privacy Tiers (Public, Private, Sensitive),
    source breakdowns, and overall document/chunk counts (Phase 6).
    """
    return await knowledge_engine.get_knowledge_summary(db)
