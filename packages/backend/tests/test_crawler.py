import asyncio
import pytest
import httpx
from httpx import AsyncClient, ASGITransport, Response
from sqlalchemy import delete
from app.main import app
from app.models.document import Document
from app.models.crawler import CrawlDomain, CrawlJob, CrawlPage
from app.core.db import init_db, get_sessionmaker
from app.crawler.allowlist import (
    is_domain_allowed,
    is_url_allowed,
    canonicalize_url,
    extract_domain,
)
from app.crawler.frontier import URLFrontier
from app.crawler.robots import RobotsManager
from app.crawler.engine import crawler_engine


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(delete(CrawlPage))
        await session.execute(delete(CrawlJob))
        await session.execute(delete(CrawlDomain))
        await session.execute(delete(Document))
        await session.commit()


def test_allowlist_domain_matching():
    allowlist = ["docs.python.org", "*.wikipedia.org", "example.com"]

    # Exact match
    assert is_domain_allowed("docs.python.org", allowlist) is True
    assert is_domain_allowed("example.com", allowlist) is True
    assert is_domain_allowed("www.example.com", allowlist) is True

    # Wildcard match
    assert is_domain_allowed("en.wikipedia.org", allowlist) is True
    assert is_domain_allowed("de.wikipedia.org", allowlist) is True

    # Subdomain match
    assert is_domain_allowed("api.example.com", allowlist) is True

    # Non-allowed
    assert is_domain_allowed("google.com", allowlist) is False
    assert is_domain_allowed("evil-wikipedia.org", allowlist) is False
    assert is_domain_allowed("notexample.com", allowlist) is False


def test_canonicalize_url():
    url1 = "https://example.com/path/?utm_source=twitter&b=2&a=1#section3"
    canonical1 = canonicalize_url(url1)
    assert canonical1 == "https://example.com/path/?a=1&b=2"

    url2 = "http://EXAMPLE.COM:80/dir/../dir/file.html"
    canonical2 = canonicalize_url(url2)
    assert "example.com/dir/file.html" in canonical2 or "example.com/file.html" in canonical2


def test_url_frontier_deduplication_and_depth():
    allowlist = ["example.com"]
    frontier = URLFrontier(allowlist=allowlist, max_depth=1, max_pages=10)

    # Add seed
    assert frontier.add_seed("https://example.com/home") is True
    # Duplicate seed rejected
    assert frontier.add_seed("https://example.com/home#anchor") is False

    # Discovered links at depth 0 -> added at depth 1
    new_links = [
        "https://example.com/about",
        "https://example.com/contact",
        "https://otherdomain.com/outside",  # not allowed
        "https://example.com/home",         # duplicate
    ]
    enqueued = frontier.enqueue_discovered_links(new_links, parent_depth=0)
    assert enqueued == 2
    assert frontier.queue_size == 3  # home + about + contact

    # Links discovered at depth 1 should be rejected because max_depth=1
    enqueued_beyond = frontier.enqueue_discovered_links(["https://example.com/subpage"], parent_depth=1)
    assert enqueued_beyond == 0


@pytest.mark.asyncio
async def test_robots_manager_compliance():
    robots_content = """
User-agent: *
Disallow: /admin/
Disallow: /private/
Crawl-delay: 2

User-agent: AegisBot
Disallow: /secret/
"""
    def mock_handler(request: httpx.Request):
        if request.url.path == "/robots.txt":
            return Response(200, text=robots_content)
        return Response(200, text="OK")

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        manager = RobotsManager()
        parser, delay = await manager.get_parser("testdomain.com", client=mock_client)
        assert delay == 2

        can_admin = await manager.can_fetch("https://testdomain.com/admin/settings", client=mock_client)
        assert can_admin is False

        can_secret = await manager.can_fetch("https://testdomain.com/secret/key", client=mock_client)
        assert can_secret is False

        can_public = await manager.can_fetch("https://testdomain.com/public/docs", client=mock_client)
        assert can_public is True


@pytest.mark.asyncio
async def test_crawler_api_domains_crud():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Add domain
        create_payload = {
            "domain": "docs.python.org",
            "description": "Python Standard Library Docs",
            "max_depth": 3,
            "rate_limit_delay": 0.5
        }
        resp = await client.post("/api/v1/crawler/domains", json=create_payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["domain"] == "docs.python.org"
        assert data["enabled"] is True
        domain_id = data["id"]

        # 2. List domains
        list_resp = await client.get("/api/v1/crawler/domains")
        assert list_resp.status_code == 200
        domains = list_resp.json()
        assert len(domains) == 1
        assert domains[0]["id"] == domain_id

        # 3. Toggle enabled
        toggle_resp = await client.patch(f"/api/v1/crawler/domains/{domain_id}/toggle")
        assert toggle_resp.status_code == 200
        assert toggle_resp.json()["enabled"] is False

        # 4. Delete domain
        del_resp = await client.delete(f"/api/v1/crawler/domains/{domain_id}")
        assert del_resp.status_code == 200

        # Verify deletion
        list_resp2 = await client.get("/api/v1/crawler/domains")
        assert len(list_resp2.json()) == 0


@pytest.mark.asyncio
async def test_crawler_execution_and_search_integration():
    """
    Tests end-to-end crawling flow:
    - Mocked website with 2 pages
    - Crawler fetches, parses HTML, discovers child link, and ingests into DB
    - Verifies Search API finds the crawled content
    """
    page1_html = """<!DOCTYPE html>
<html>
<head><title>Quantum Computing Primer</title></head>
<body>
    <h1>Introduction to Qubits</h1>
    <p>Superconducting circuits and ion traps are prominent hardware paradigms.</p>
    <a href="/algorithms.html">Quantum Algorithms Overview</a>
</body>
</html>"""

    page2_html = """<!DOCTYPE html>
<html>
<head><title>Quantum Algorithms Overview</title></head>
<body>
    <h1>Shor and Grover Algorithms</h1>
    <p>Shor's algorithm provides exponential speedup for integer factorization.</p>
</body>
</html>"""

    def mock_server(request: httpx.Request):
        url = str(request.url)
        if "robots.txt" in url:
            return Response(200, text="User-agent: *\nAllow: /")
        elif "algorithms.html" in url:
            return Response(200, headers={"Content-Type": "text/html"}, text=page2_html)
        else:
            return Response(200, headers={"Content-Type": "text/html"}, text=page1_html)

    mock_transport = httpx.MockTransport(mock_server)
    mock_client = httpx.AsyncClient(transport=mock_transport)

    sm = get_sessionmaker()
    # 1. Setup allowlist domain
    async with sm() as session:
        dom = CrawlDomain(domain="quantum.test", enabled=True, max_depth=2, rate_limit_delay=0.1)
        session.add(dom)
        job = CrawlJob(
            seed_url="https://quantum.test/intro.html",
            domain="quantum.test",
            status="queued",
            max_depth=2,
            max_pages=5
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    # 2. Run crawl job directly using mock client
    task = await crawler_engine.start_crawl_job(
        job_id=job_id,
        seed_url="https://quantum.test/intro.html",
        allowlist=["quantum.test"],
        max_depth=2,
        max_pages=5,
        rate_limit_delay=0.01,
        custom_client=mock_client
    )
    await task

    # 3. Verify job status and pages in DB
    async with sm() as session:
        from sqlalchemy import select
        res_job = await session.execute(select(CrawlJob).where(CrawlJob.id == job_id))
        crawled_job = res_job.scalar_one()
        assert crawled_job.status == "completed"
        assert crawled_job.pages_crawled >= 2

        res_pages = await session.execute(select(CrawlPage).where(CrawlPage.job_id == job_id))
        pages = res_pages.scalars().all()
        assert len(pages) >= 2
        assert any("algorithms" in p.url for p in pages)

    # 4. Verify search integration: search for "factorization"
    api_transport = ASGITransport(app=app)
    async with AsyncClient(transport=api_transport, base_url="http://test") as client:
        search_resp = await client.get("/api/v1/search?q=factorization&source_type=web")
        assert search_resp.status_code == 200
        results = search_resp.json()["results"]
        assert len(results) >= 1
        assert results[0]["source_type"] == "web"
        assert "Shor" in results[0]["snippet"] or "factorization" in results[0]["snippet"]
