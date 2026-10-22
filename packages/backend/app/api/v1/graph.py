from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_async_session
from app.services.knowledge_graph import knowledge_graph_service

router = APIRouter(prefix="/graph", tags=["Knowledge Graph"])


class GraphExtractResponse(BaseModel):
    document_id: str
    document_title: str
    entities_found: int
    relations_created: int
    groundings_recorded: int


@router.get("")
async def get_graph(
    query: Optional[str] = Query(None, description="Filter nodes by entity name, canonical name or description"),
    entity_type: Optional[str] = Query(None, description="Comma-separated entity types (e.g. TECHNOLOGY,CONCEPT,ORGANIZATION)"),
    min_weight: float = Query(0.5, ge=0.0, le=100.0, description="Minimum relationship weight threshold"),
    limit_nodes: int = Query(100, ge=1, le=500, description="Maximum nodes to return"),
    limit_edges: int = Query(200, ge=1, le=1000, description="Maximum edges to return"),
    db: AsyncSession = Depends(get_async_session)
) -> Dict[str, Any]:
    """
    Retrieve the Grounded Knowledge Graph topology (nodes, edges, node degrees, entity types)
    for interactive visual force layout (Phase 7).
    """
    types_list = [t.strip().upper() for t in entity_type.split(",") if t.strip()] if entity_type else None
    return await knowledge_graph_service.get_graph(
        db=db,
        query=query,
        entity_types=types_list,
        min_weight=min_weight,
        limit_nodes=limit_nodes,
        limit_edges=limit_edges
    )


@router.get("/stats")
async def get_graph_stats(
    db: AsyncSession = Depends(get_async_session)
) -> Dict[str, Any]:
    """
    Get aggregated graph metrics: total nodes, edges, groundings,
    entity type breakdowns, and top hub entities.
    """
    return await knowledge_graph_service.get_stats(db)


@router.get("/search")
async def search_entities(
    query: str = Query(..., min_length=1, description="Entity search query"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session)
) -> List[Dict[str, Any]]:
    """
    Search entities with autocomplete matching across canonical names and aliases.
    """
    return await knowledge_graph_service.search_entities(
        db=db,
        query=query,
        entity_type=entity_type,
        limit=limit
    )


@router.get("/entity/{entity_id}")
async def get_entity_details(
    entity_id: str,
    db: AsyncSession = Depends(get_async_session)
) -> Dict[str, Any]:
    """
    Get deep entity details, connected incoming/outgoing relationships,
    and all physical grounded source citations (document title, chunk anchor, exact quote).
    """
    details = await knowledge_graph_service.get_entity_details(db, entity_id)
    if not details:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity '{entity_id}' not found."
        )
    return details


@router.get("/subgraph")
async def get_subgraph(
    entity_id: str = Query(..., description="Target center entity ID"),
    depth: int = Query(1, ge=1, le=2, description="Hop depth (1 or 2)"),
    db: AsyncSession = Depends(get_async_session)
) -> Dict[str, Any]:
    """
    Extract an ego-subgraph centered around an entity with 1-hop or 2-hop radius.
    """
    return await knowledge_graph_service.get_subgraph(db, entity_id, depth)


@router.post("/extract/{document_id}")
async def extract_document_graph(
    document_id: str,
    db: AsyncSession = Depends(get_async_session)
) -> Dict[str, Any]:
    """
    Trigger grounded entity and relationship extraction for a specific document.
    """
    res = await knowledge_graph_service.extract_from_document(db, document_id)
    if "error" in res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=res["error"]
        )
    return res


@router.post("/extract-all")
async def extract_all_documents_graph(
    db: AsyncSession = Depends(get_async_session)
) -> Dict[str, Any]:
    """
    Batch extract and rebuild the Grounded Knowledge Graph across all documents in PostgreSQL.
    """
    return await knowledge_graph_service.extract_from_all_documents(db)


@router.delete("/entity/{entity_id}")
async def delete_entity(
    entity_id: str,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Delete an entity node and cascade-delete its edges and groundings.
    """
    deleted = await knowledge_graph_service.delete_entity(db, entity_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity '{entity_id}' not found."
        )
    return {"status": "success", "message": f"Entity '{entity_id}' deleted."}
