from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_async_session
from app.services.source_manager import source_manager
from app.core.logging import logger

router = APIRouter(prefix="/sources", tags=["Sources"])


class SourceUpdatePayload(BaseModel):
    enabled: Optional[bool] = Field(None, description="Whether to include source in search and indexing")
    default_privacy_tier: Optional[str] = Field(None, pattern="^(public|private|sensitive)$", description="Default privacy tier")
    display_name: Optional[str] = Field(None, description="Human-readable source name")
    description: Optional[str] = Field(None, description="Source description")


class SourceTogglePayload(BaseModel):
    source_type: str = Field(..., description="Source identifier (e.g. upload, note, code, web)")
    enabled: bool = Field(..., description="Target enabled status")


class SourceItem(BaseModel):
    source_type: str
    display_name: str
    enabled: bool
    default_privacy_tier: str
    description: Optional[str] = None
    icon: Optional[str] = None
    document_count: int = 0
    chunk_count: int = 0
    updated_at: Optional[str] = None


@router.get("", response_model=List[SourceItem])
async def list_sources(
    db: AsyncSession = Depends(get_async_session)
):
    """
    List all registered intelligence sources with their enabled/disabled state,
    default privacy tier, and live document/chunk metrics (Phase 6).
    """
    return await source_manager.list_sources(db)


@router.patch("/{source_type}")
async def update_source_config(
    source_type: str,
    payload: SourceUpdatePayload,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update configuration for a specific intelligence source.
    """
    updated = await source_manager.update_source(
        db=db,
        source_type=source_type,
        enabled=payload.enabled,
        default_privacy_tier=payload.default_privacy_tier,
        display_name=payload.display_name,
        description=payload.description
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Source '{source_type}' not found.")
    return updated


@router.post("/toggle")
async def toggle_source(
    payload: SourceTogglePayload,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Quick toggle enable/disable for an intelligence source (Phase 6).
    """
    updated = await source_manager.toggle_source(
        db=db,
        source_type=payload.source_type,
        enabled=payload.enabled
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Source '{payload.source_type}' not found.")
    return updated
