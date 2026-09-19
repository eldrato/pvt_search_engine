import asyncio
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import httpx
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.db import get_sessionmaker
from app.core.logging import logger
from app.models.crawler import CrawlJob, CrawlPage, CrawlDomain
from app.crawler.allowlist import (
    canonicalize_url,
    extract_domain,
    is_url_allowed,
)
from app.crawler.robots import robots_manager, USER_AGENT
from app.crawler.frontier import URLFrontier
from app.services.ingestion import IngestionService


class WebCrawlerEngine:
    def __init__(self):
        self.ingestion_service = IngestionService()
        self._active_jobs: Dict[str, asyncio.Task] = {}
        self._cancel_flags: Dict[str, bool] = {}

    def is_job_running(self, job_id: str) -> bool:
        task = self._active_jobs.get(job_id)
        return task is not None and not task.done()

    def cancel_job(self, job_id: str) -> bool:
        if job_id in self._active_jobs:
            self._cancel_flags[job_id] = True
            task = self._active_jobs[job_id]
            task.cancel()
            return True
        return False

    async def start_crawl_job(
        self,
        job_id: str,
        seed_url: str,
        allowlist: List[str],
        max_depth: int = 2,
        max_pages: int = 20,
        rate_limit_delay: float = 1.0,
        custom_client: Optional[httpx.AsyncClient] = None
    ):
        """
        Launches crawl execution loop in the background or awaited directly.
        """
        self._cancel_flags[job_id] = False
        task = asyncio.create_task(
            self._run_crawl(
                job_id=job_id,
                seed_url=seed_url,
                allowlist=allowlist,
                max_depth=max_depth,
                max_pages=max_pages,
                rate_limit_delay=rate_limit_delay,
                custom_client=custom_client
            )
        )
        self._active_jobs[job_id] = task
        return task

    async def _run_crawl(
        self,
        job_id: str,
        seed_url: str,
        allowlist: List[str],
        max_depth: int,
        max_pages: int,
        rate_limit_delay: float,
        custom_client: Optional[httpx.AsyncClient] = None
    ):
        sm = get_sessionmaker()

        # 1. Update job status to running
        async with sm() as session:
            await session.execute(
                update(CrawlJob)
                .where(CrawlJob.id == job_id)
                .values(
                    status="running",
                    started_at=datetime.now(timezone.utc),
                    current_url=seed_url
                )
            )
            await session.commit()

        frontier = URLFrontier(
            allowlist=allowlist,
            max_depth=max_depth,
            max_pages=max_pages
        )

        frontier.add_seed(seed_url)

        own_client = False
        client = custom_client
        if client is None:
            client = httpx.AsyncClient(
                timeout=10.0,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT}
            )
            own_client = True

        pages_crawled = 0
        pages_failed = 0
        last_request_time = 0.0

        try:
            while not frontier.is_complete():
                if self._cancel_flags.get(job_id, False):
                    logger.info(f"Crawl job {job_id} cancelled by user.")
                    break

                item = frontier.pop_next()
                if not item:
                    break

                current_url, depth = item
                domain = extract_domain(current_url)

                # Check robots.txt compliance
                can_crawl = await robots_manager.can_fetch(current_url, client=client)
                if not can_crawl:
                    logger.info(f"Skipping {current_url}: disallowed by robots.txt")
                    pages_failed += 1
                    async with sm() as session:
                        page_record = CrawlPage(
                            job_id=job_id,
                            url=current_url,
                            canonical_url=canonicalize_url(current_url),
                            status_code=403,
                            depth=depth,
                            error_message="Disallowed by robots.txt"
                        )
                        session.add(page_record)
                        await session.commit()
                    continue

                # Politeness delay
                now = asyncio.get_event_loop().time()
                elapsed = now - last_request_time
                if elapsed < rate_limit_delay and last_request_time > 0:
                    await asyncio.sleep(rate_limit_delay - elapsed)

                # Update current URL in job record
                async with sm() as session:
                    await session.execute(
                        update(CrawlJob)
                        .where(CrawlJob.id == job_id)
                        .values(current_url=current_url)
                    )
                    await session.commit()

                # Fetch page
                last_request_time = asyncio.get_event_loop().time()
                try:
                    resp = await client.get(current_url)
                except Exception as req_err:
                    logger.warning(f"Failed to fetch {current_url}: {req_err}")
                    pages_failed += 1
                    async with sm() as session:
                        page_rec = CrawlPage(
                            job_id=job_id,
                            url=current_url,
                            canonical_url=canonicalize_url(current_url),
                            status_code=0,
                            depth=depth,
                            error_message=str(req_err)
                        )
                        session.add(page_rec)
                        await session.commit()
                    continue

                if resp.status_code != 200:
                    logger.info(f"Non-200 response for {current_url}: {resp.status_code}")
                    pages_failed += 1
                    async with sm() as session:
                        page_rec = CrawlPage(
                            job_id=job_id,
                            url=current_url,
                            canonical_url=canonicalize_url(current_url),
                            status_code=resp.status_code,
                            depth=depth,
                            error_message=f"HTTP status {resp.status_code}"
                        )
                        session.add(page_rec)
                        await session.commit()
                    continue

                # Check content type (must be HTML or text)
                content_type = resp.headers.get("content-type", "").lower()
                if "html" not in content_type and "text" not in content_type:
                    logger.info(f"Skipping non-HTML resource at {current_url}: {content_type}")
                    continue

                html_content = resp.text
                html_bytes = resp.content

                # Discover child links
                discovered_links = self._extract_links(html_content, base_url=current_url)
                frontier.enqueue_discovered_links(discovered_links, parent_depth=depth)

                # Extract page title
                soup = BeautifulSoup(html_content, "html.parser")
                title = soup.title.string.strip() if soup.title and soup.title.string else current_url

                # Ingest into Aegis SSOT & Search Index
                doc_meta = {
                    "url": current_url,
                    "canonical_url": canonicalize_url(current_url),
                    "domain": domain,
                    "crawl_job_id": job_id,
                    "depth": depth,
                    "crawled_at": datetime.now(timezone.utc).isoformat()
                }

                doc_id = None
                content_hash = None
                try:
                    async with sm() as session:
                        ingest_result = await self.ingestion_service.ingest_file(
                            content=html_bytes,
                            filename=f"{domain}_{title[:30]}.html",
                            mime_type="text/html",
                            source_type="web",
                            doc_metadata=doc_meta,
                            db=session
                        )
                        doc_info = ingest_result.get("document", {})
                        doc_id = doc_info.get("id")
                        content_hash = doc_info.get("content_hash")
                except Exception as ingest_err:
                    logger.error(f"Failed to ingest crawled page {current_url}: {ingest_err}")

                frontier.record_crawled()
                pages_crawled += 1

                # Record CrawlPage
                async with sm() as session:
                    page_rec = CrawlPage(
                        job_id=job_id,
                        url=current_url,
                        canonical_url=canonicalize_url(current_url),
                        status_code=resp.status_code,
                        title=title[:512],
                        content_hash=content_hash,
                        document_id=doc_id,
                        depth=depth
                    )
                    session.add(page_rec)

                    # Update domain stats
                    if domain:
                        await session.execute(
                            update(CrawlDomain)
                            .where(CrawlDomain.domain == domain)
                            .values(
                                pages_crawled=CrawlDomain.pages_crawled + 1,
                                last_crawled_at=datetime.now(timezone.utc)
                            )
                        )

                    # Update job stats
                    await session.execute(
                        update(CrawlJob)
                        .where(CrawlJob.id == job_id)
                        .values(
                            pages_crawled=pages_crawled,
                            pages_failed=pages_failed
                        )
                    )
                    await session.commit()

            # Finalize job status
            final_status = "cancelled" if self._cancel_flags.get(job_id, False) else "completed"
            async with sm() as session:
                await session.execute(
                    update(CrawlJob)
                    .where(CrawlJob.id == job_id)
                    .values(
                        status=final_status,
                        completed_at=datetime.now(timezone.utc),
                        current_url=None
                    )
                )
                await session.commit()

            logger.info(f"Crawl job {job_id} {final_status}: crawled {pages_crawled}, failed {pages_failed}")

        except asyncio.CancelledError:
            async with sm() as session:
                await session.execute(
                    update(CrawlJob)
                    .where(CrawlJob.id == job_id)
                    .values(
                        status="cancelled",
                        completed_at=datetime.now(timezone.utc),
                        current_url=None
                    )
                )
                await session.commit()
            logger.info(f"Crawl job {job_id} cancelled.")

        except Exception as e:
            logger.error(f"Crawl job {job_id} encountered fatal error: {e}", exc_info=True)
            async with sm() as session:
                await session.execute(
                    update(CrawlJob)
                    .where(CrawlJob.id == job_id)
                    .values(
                        status="failed",
                        error_message=str(e),
                        completed_at=datetime.now(timezone.utc),
                        current_url=None
                    )
                )
                await session.commit()

        finally:
            if own_client and client:
                await client.aclose()
            self._active_jobs.pop(job_id, None)
            self._cancel_flags.pop(job_id, None)

    def _extract_links(self, html: str, base_url: str) -> List[str]:
        soup = BeautifulSoup(html, "html.parser")
        links = []
        skip_extensions = (
            ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z",
            ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
            ".mp3", ".mp4", ".avi", ".mov", ".mkv",
            ".exe", ".dmg", ".bin", ".iso"
        )

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue

            try:
                resolved = urllib.parse.urljoin(base_url, href)
                parsed = urllib.parse.urlparse(resolved)
                if parsed.scheme not in ("http", "https"):
                    continue

                path_lower = parsed.path.lower()
                if any(path_lower.endswith(ext) for ext in skip_extensions):
                    continue

                links.append(resolved)
            except Exception:
                continue

        return links


crawler_engine = WebCrawlerEngine()
