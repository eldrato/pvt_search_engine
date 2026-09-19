from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, desc

from app.core.db import get_async_session
from app.models.crawler import CrawlDomain, CrawlJob, CrawlPage
from app.crawler.allowlist import normalize_domain, extract_domain, is_domain_allowed
from app.crawler.engine import crawler_engine

router = APIRouter(prefix="/crawler", tags=["Web Crawler"])


# --- Schemas ---

class CrawlDomainCreate(BaseModel):
    domain: str = Field(..., description="Domain name (e.g., 'news.ycombinator.com', '*.python.org')")
    description: Optional[str] = Field(None, description="Personal notes or source description")
    max_depth: int = Field(2, ge=1, le=5, description="Default maximum crawl depth")
    rate_limit_delay: float = Field(1.0, ge=0.2, le=10.0, description="Politeness delay in seconds")


class CrawlDomainResponse(BaseModel):
    id: str
    domain: str
    description: Optional[str] = None
    enabled: bool
    max_depth: int
    rate_limit_delay: float
    pages_crawled: int
    last_crawled_at: Optional[str] = None
    created_at: Optional[str] = None


class CrawlJobCreate(BaseModel):
    seed_url: str = Field(..., description="Seed URL to begin crawling from")
    max_depth: int = Field(2, ge=1, le=5, description="Maximum crawl depth from seed URL")
    max_pages: int = Field(20, ge=1, le=100, description="Maximum total pages to crawl")
    rate_limit_delay: Optional[float] = Field(None, ge=0.1, le=10.0, description="Politeness delay between requests")


class CrawlJobResponse(BaseModel):
    id: str
    seed_url: str
    domain: str
    status: str
    max_depth: int
    max_pages: int
    pages_crawled: int
    pages_failed: int
    current_url: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None


class CrawlPageItem(BaseModel):
    id: str
    url: str
    canonical_url: str
    status_code: int
    title: Optional[str] = None
    document_id: Optional[str] = None
    depth: int
    error_message: Optional[str] = None
    crawled_at: Optional[str] = None


class CrawlJobDetailResponse(CrawlJobResponse):
    pages: List[CrawlPageItem] = []


# --- Domain Allowlist Endpoints ---

@router.get("/domains", response_model=List[CrawlDomainResponse])
async def list_domains(db: AsyncSession = Depends(get_async_session)):
    """List all configured allowlisted domains."""
    res = await db.execute(select(CrawlDomain).order_by(desc(CrawlDomain.created_at)))
    domains = res.scalars().all()
    return [d.to_dict() for d in domains]


@router.post("/domains", response_model=CrawlDomainResponse, status_code=status.HTTP_201_CREATED)
async def add_domain(
    payload: CrawlDomainCreate,
    db: AsyncSession = Depends(get_async_session)
):
    """Add a new domain to the strict crawling allowlist."""
    clean_dom = normalize_domain(payload.domain)
    if not clean_dom:
        raise HTTPException(status_code=400, detail="Invalid domain name")

    # Check for existing
    res = await db.execute(select(CrawlDomain).where(CrawlDomain.domain == clean_dom))
    existing = res.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Domain '{clean_dom}' is already allowlisted")

    dom = CrawlDomain(
        domain=clean_dom,
        description=payload.description,
        max_depth=payload.max_depth,
        rate_limit_delay=payload.rate_limit_delay,
        enabled=True
    )
    db.add(dom)
    await db.commit()
    await db.refresh(dom)
    return dom.to_dict()


@router.delete("/domains/{domain_id}", status_code=status.HTTP_200_OK)
async def delete_domain(
    domain_id: str,
    db: AsyncSession = Depends(get_async_session)
):
    """Remove a domain from the allowlist."""
    res = await db.execute(select(CrawlDomain).where(CrawlDomain.id == domain_id))
    dom = res.scalar_one_or_none()
    if not dom:
        raise HTTPException(status_code=404, detail="Domain not found")

    await db.delete(dom)
    await db.commit()
    return {"message": f"Domain '{dom.domain}' removed from allowlist"}


@router.patch("/domains/{domain_id}/toggle", response_model=CrawlDomainResponse)
async def toggle_domain(
    domain_id: str,
    db: AsyncSession = Depends(get_async_session)
):
    """Toggle enabled status of an allowlisted domain."""
    res = await db.execute(select(CrawlDomain).where(CrawlDomain.id == domain_id))
    dom = res.scalar_one_or_none()
    if not dom:
        raise HTTPException(status_code=404, detail="Domain not found")

    dom.enabled = not dom.enabled
    await db.commit()
    await db.refresh(dom)
    return dom.to_dict()


# --- Crawl Job Endpoints ---

@router.post("/jobs", response_model=CrawlJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_crawl_job(
    payload: CrawlJobCreate,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Initiate a controlled crawl job starting from seed_url.
    The domain of seed_url must be allowlisted and enabled.
    """
    domain = extract_domain(payload.seed_url)
    if not domain:
        raise HTTPException(status_code=400, detail="Invalid seed URL")

    # Fetch active allowlist
    res = await db.execute(select(CrawlDomain).where(CrawlDomain.enabled == True))  # noqa: E712
    allowlist_records = res.scalars().all()
    allowlist_domains = [d.domain for d in allowlist_records]

    if not is_domain_allowed(domain, allowlist_domains):
        # Auto-allowlist if no domains exist yet, or reject
        if len(allowlist_domains) == 0:
            auto_dom = CrawlDomain(domain=domain, description="Auto-added on first crawl", enabled=True)
            db.add(auto_dom)
            await db.flush()
            allowlist_domains.append(domain)
        else:
            raise HTTPException(
                status_code=403,
                detail=f"Domain '{domain}' is not in the allowlist. Please add it to the allowlist before crawling."
            )

    # Determine rate limit delay
    rate_delay = payload.rate_limit_delay
    if rate_delay is None:
        matching_dom = next((d for d in allowlist_records if d.domain == domain), None)
        rate_delay = matching_dom.rate_limit_delay if matching_dom else 1.0

    # Create Job record
    job = CrawlJob(
        seed_url=payload.seed_url,
        domain=domain,
        status="queued",
        max_depth=payload.max_depth,
        max_pages=payload.max_pages,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Launch crawler task in background
    await crawler_engine.start_crawl_job(
        job_id=job.id,
        seed_url=payload.seed_url,
        allowlist=allowlist_domains,
        max_depth=payload.max_depth,
        max_pages=payload.max_pages,
        rate_limit_delay=rate_delay
    )

    return job.to_dict()


@router.get("/jobs", response_model=List[CrawlJobResponse])
async def list_crawl_jobs(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session)
):
    """List recent crawl jobs."""
    res = await db.execute(
        select(CrawlJob)
        .order_by(desc(CrawlJob.created_at))
        .limit(limit)
    )
    jobs = res.scalars().all()
    return [j.to_dict() for j in jobs]


@router.get("/jobs/{job_id}", response_model=CrawlJobDetailResponse)
async def get_crawl_job(
    job_id: str,
    db: AsyncSession = Depends(get_async_session)
):
    """Retrieve details and crawled pages for a specific crawl job."""
    res = await db.execute(select(CrawlJob).where(CrawlJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found")

    pages_res = await db.execute(
        select(CrawlPage)
        .where(CrawlPage.job_id == job_id)
        .order_by(desc(CrawlPage.crawled_at))
        .limit(100)
    )
    pages = pages_res.scalars().all()

    data = job.to_dict()
    data["pages"] = [p.to_dict() for p in pages]
    return data


@router.post("/jobs/{job_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_crawl_job(
    job_id: str,
    db: AsyncSession = Depends(get_async_session)
):
    """Cancel an active crawl job."""
    res = await db.execute(select(CrawlJob).where(CrawlJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found")

    if job.status not in ("queued", "running"):
        return {"message": f"Job is already {job.status}"}

    cancelled = crawler_engine.cancel_job(job_id)
    job.status = "cancelled"
    job.completed_at = datetime.now(timezone.utc)
    await db.commit()

    return {"message": "Crawl job cancellation requested", "success": True}
