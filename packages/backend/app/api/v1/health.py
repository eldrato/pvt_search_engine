import time
import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import settings
from app.core.db import get_async_session
from app.core.logging import logger

router = APIRouter(prefix="/health", tags=["Health"])


class ServiceHealth(BaseModel):
    status: str = Field(..., description="Service status: healthy, degraded, or unreachable")
    latency_ms: float = Field(..., description="Response latency in milliseconds")
    details: dict = Field(default_factory=dict, description="Detailed status metrics")


class SystemHealthResponse(BaseModel):
    status: str = Field(..., description="Overall system health status")
    version: str
    environment: str
    services: dict[str, ServiceHealth]


@router.get("", response_model=SystemHealthResponse, status_code=status.HTTP_200_OK)
async def check_system_health(db: AsyncSession = Depends(get_async_session)) -> SystemHealthResponse:
    services: dict[str, ServiceHealth] = {}
    overall_healthy = True

    # 1. PostgreSQL Check
    start_time = time.perf_counter()
    try:
        res = await db.execute(text("SELECT 1"))
        _ = res.scalar()
        latency = (time.perf_counter() - start_time) * 1000
        services["postgres"] = ServiceHealth(
            status="healthy",
            latency_ms=round(latency, 2),
            details={"engine": "PostgreSQL 16 (SSOT)", "role": "Single Source of Truth"}
        )
    except Exception as e:
        overall_healthy = False
        logger.error(f"PostgreSQL health check failed: {e}")
        services["postgres"] = ServiceHealth(
            status="unreachable",
            latency_ms=round((time.perf_counter() - start_time) * 1000, 2),
            details={"error": str(e)}
        )

    # 2. OpenSearch Check
    start_time = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.OPENSEARCH_URL}/_cluster/health")
            latency = (time.perf_counter() - start_time) * 1000
            if resp.status_code == 200:
                data = resp.json()
                services["opensearch"] = ServiceHealth(
                    status="healthy" if data.get("status") in ["green", "yellow"] else "degraded",
                    latency_ms=round(latency, 2),
                    details={"cluster_status": data.get("status"), "number_of_nodes": data.get("number_of_nodes")}
                )
            else:
                overall_healthy = False
                services["opensearch"] = ServiceHealth(
                    status="degraded",
                    latency_ms=round(latency, 2),
                    details={"status_code": resp.status_code}
                )
    except Exception as e:
        overall_healthy = False
        logger.error(f"OpenSearch health check failed: {e}")
        services["opensearch"] = ServiceHealth(
            status="unreachable",
            latency_ms=round((time.perf_counter() - start_time) * 1000, 2),
            details={"error": str(e)}
        )

    # 3. Qdrant Check
    start_time = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.QDRANT_URL}/healthz")
            latency = (time.perf_counter() - start_time) * 1000
            if resp.status_code == 200:
                services["qdrant"] = ServiceHealth(
                    status="healthy",
                    latency_ms=round(latency, 2),
                    details={"vector_store": "Qdrant HNSW"}
                )
            else:
                overall_healthy = False
                services["qdrant"] = ServiceHealth(
                    status="degraded",
                    latency_ms=round(latency, 2),
                    details={"status_code": resp.status_code}
                )
    except Exception as e:
        overall_healthy = False
        logger.error(f"Qdrant health check failed: {e}")
        services["qdrant"] = ServiceHealth(
            status="unreachable",
            latency_ms=round((time.perf_counter() - start_time) * 1000, 2),
            details={"error": str(e)}
        )

    # 4. Redis Check
    start_time = time.perf_counter()
    try:
        r = aioredis.from_url(settings.REDIS_URL)
        pong = await r.ping()
        await r.aclose()
        latency = (time.perf_counter() - start_time) * 1000
        if pong:
            services["redis"] = ServiceHealth(
                status="healthy",
                latency_ms=round(latency, 2),
                details={"cache": "Redis 7"}
            )
        else:
            overall_healthy = False
            services["redis"] = ServiceHealth(
                status="degraded",
                latency_ms=round(latency, 2),
                details={"response": str(pong)}
            )
    except Exception as e:
        overall_healthy = False
        logger.error(f"Redis health check failed: {e}")
        services["redis"] = ServiceHealth(
            status="unreachable",
            latency_ms=round((time.perf_counter() - start_time) * 1000, 2),
            details={"error": str(e)}
        )

    return SystemHealthResponse(
        status="healthy" if overall_healthy else "degraded",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        services=services
    )
