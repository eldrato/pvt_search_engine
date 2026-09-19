from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_async_session
from app.services.search import search_service
from app.evaluation.retrieval_benchmark import retrieval_benchmark

router = APIRouter(prefix="/evaluation", tags=["Evaluation"])


@router.get("/benchmark")
async def run_retrieval_benchmark_endpoint(
    modes: Optional[List[str]] = Query(None, description="Retrieval modes to evaluate (default: lexical, semantic, hybrid)"),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Executes automated IR retrieval benchmark suite comparing Lexical, Semantic, and Hybrid RRF modes.
    Computes Precision@K, Recall@K, MRR, and NDCG@K across gold-standard evaluation queries.
    """
    selected_modes = modes or ["lexical", "semantic", "hybrid"]
    report = await retrieval_benchmark.evaluate_engine(
        search_fn=search_service.search,
        modes=selected_modes,
        db=db
    )
    return report
