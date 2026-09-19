from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_async_session
from app.services.search import search_service
from app.ranking.scorer import ScoreBreakdown

router = APIRouter(prefix="/search", tags=["Search"])


class SearchHit(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    snippet: str
    content: str
    score: float
    source_type: str
    mime_type: str
    anchor_label: str
    chunk_index: int
    location_meta: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    score_breakdown: Optional[ScoreBreakdown] = None


class SearchResponse(BaseModel):
    query: str
    total: int
    latency_ms: float
    engine: str
    results: List[SearchHit]


@router.get("", response_model=SearchResponse)
async def lexical_search(
    q: str = Query(..., min_length=1, description="Keyword search query"),
    source_type: Optional[str] = Query(None, description="Filter by source type (upload, note, code, web)"),
    limit: int = Query(20, ge=1, le=100, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Search ingested personal intelligence using BM25 keyword matching with query highlighting and precision anchors.
    """
    results = await search_service.search(
        query=q,
        source_type=source_type,
        limit=limit,
        offset=offset,
        db=db
    )
    return results
