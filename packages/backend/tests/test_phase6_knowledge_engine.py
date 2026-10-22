import os
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete
from app.main import app
from app.models.document import Document, DocumentChunk
from app.models.source import SourceConfig
from app.core.db import init_db, get_sessionmaker
from app.services.qdrant import qdrant_service

os.environ["AEGIS_OFFLINE_EMBEDDER"] = "true"


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(delete(DocumentChunk))
        await session.execute(delete(Document))
        await session.commit()
    if qdrant_service.client:
        try:
            qdrant_service.client.delete_collection(qdrant_service.collection_name)
            qdrant_service.init_collection()
        except Exception:
            pass


@pytest.mark.asyncio
async def test_sources_listing_and_toggles():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. List default sources
        resp = await client.get("/api/v1/sources")
        assert resp.status_code == 200
        sources = resp.json()
        assert len(sources) >= 4
        source_types = [s["source_type"] for s in sources]
        assert "upload" in source_types
        assert "note" in source_types
        assert "code" in source_types
        assert "web" in source_types

        # 2. Update source configuration
        patch_resp = await client.patch("/api/v1/sources/web", json={
            "enabled": False,
            "default_privacy_tier": "public"
        })
        assert patch_resp.status_code == 200
        updated = patch_resp.json()
        assert updated["enabled"] is False

        # 3. Quick toggle endpoint
        toggle_resp = await client.post("/api/v1/sources/toggle", json={
            "source_type": "web",
            "enabled": True
        })
        assert toggle_resp.status_code == 200
        toggled = toggle_resp.json()
        assert toggled["enabled"] is True


@pytest.mark.asyncio
async def test_document_ingestion_with_privacy_tiers():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Ingest note with explicit sensitive tier
        sensitive_payload = {
            "title": "Secret Passwords and Encryption Keys",
            "content": "Super confidential AES-256 master key for private infrastructure.",
            "source_type": "note",
            "privacy_tier": "sensitive"
        }
        res1 = await client.post("/api/v1/documents/text", json=sensitive_payload)
        assert res1.status_code == 201
        doc1 = res1.json()["document"]
        assert doc1["privacy_tier"] == "sensitive"

        # Ingest note with default tier (inherits 'private' from note source config)
        normal_payload = {
            "title": "Daily Journal Entry",
            "content": "Reflecting on hybrid search engine architecture and performance.",
            "source_type": "note"
        }
        res2 = await client.post("/api/v1/documents/text", json=normal_payload)
        assert res2.status_code == 201
        doc2 = res2.json()["document"]
        assert doc2["privacy_tier"] == "private"


@pytest.mark.asyncio
async def test_document_reclassification_and_batch():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/v1/documents/text", json={
            "title": "Public Blog Draft",
            "content": "A blog post discussing privacy-first search engines.",
            "source_type": "note"
        })
        assert res.status_code == 201
        doc_id = res.json()["document"]["id"]

        # Reclassify to public
        patch_resp = await client.patch(f"/api/v1/documents/{doc_id}/classification", json={
            "privacy_tier": "public"
        })
        assert patch_resp.status_code == 200
        assert patch_resp.json()["privacy_tier"] == "public"

        # Verify via detail view
        get_resp = await client.get(f"/api/v1/documents/{doc_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["privacy_tier"] == "public"

        # Batch classify
        batch_resp = await client.post("/api/v1/documents/batch-classify", json={
            "document_ids": [doc_id],
            "privacy_tier": "sensitive"
        })
        assert batch_resp.status_code == 200
        assert batch_resp.json()["updated_count"] == 1

        get_resp2 = await client.get(f"/api/v1/documents/{doc_id}")
        assert get_resp2.json()["privacy_tier"] == "sensitive"


@pytest.mark.asyncio
async def test_privacy_tier_search_filtering():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Document 1: Public
        await client.post("/api/v1/documents/text", json={
            "title": "Public Guide to Aegis",
            "content": "Aegis engine provides fast hybrid searching for all researchers.",
            "source_type": "note",
            "privacy_tier": "public"
        })

        # Document 2: Sensitive
        await client.post("/api/v1/documents/text", json={
            "title": "Confidential Aegis Vault",
            "content": "Aegis engine vault credentials and sensitive production secrets.",
            "source_type": "note",
            "privacy_tier": "sensitive"
        })

        # 1. Search with privacy_tier=public
        pub_search = await client.get("/api/v1/search?q=Aegis&privacy_tier=public")
        assert pub_search.status_code == 200
        pub_data = pub_search.json()
        assert pub_data["total"] == 1
        assert pub_data["results"][0]["title"] == "Public Guide to Aegis"
        assert pub_data["results"][0]["privacy_tier"] == "public"

        # 2. Search with privacy_tier=sensitive
        sens_search = await client.get("/api/v1/search?q=Aegis&privacy_tier=sensitive")
        assert sens_search.status_code == 200
        sens_data = sens_search.json()
        assert sens_data["total"] == 1
        assert sens_data["results"][0]["title"] == "Confidential Aegis Vault"
        assert sens_data["results"][0]["privacy_tier"] == "sensitive"

        # 3. Search with include_sensitive=false
        nosens_search = await client.get("/api/v1/search?q=Aegis&include_sensitive=false")
        assert nosens_search.status_code == 200
        nosens_data = nosens_search.json()
        assert nosens_data["total"] == 1
        assert nosens_data["results"][0]["title"] == "Public Guide to Aegis"


@pytest.mark.asyncio
async def test_source_disable_excludes_from_search():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Ingest note and code documents
        await client.post("/api/v1/documents/text", json={
            "title": "Kubernetes Deployment Code",
            "content": "apiVersion apps v1 kind Deployment metadata name aegis cluster",
            "source_type": "code"
        })

        # Verify search finds it while code source is enabled
        s1 = await client.get("/api/v1/search?q=cluster")
        assert s1.status_code == 200
        assert s1.json()["total"] == 1

        # Disable code source
        await client.post("/api/v1/sources/toggle", json={
            "source_type": "code",
            "enabled": False
        })

        # Search should now exclude code source
        s2 = await client.get("/api/v1/search?q=cluster")
        assert s2.status_code == 200
        assert s2.json()["total"] == 0

        # Re-enable code source
        await client.post("/api/v1/sources/toggle", json={
            "source_type": "code",
            "enabled": True
        })
        s3 = await client.get("/api/v1/search?q=cluster")
        assert s3.status_code == 200
        assert s3.json()["total"] == 1


@pytest.mark.asyncio
async def test_knowledge_summary_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Ingest documents in various tiers
        await client.post("/api/v1/documents/text", json={
            "title": "Public Research Paper",
            "content": "Machine learning retrieval models and dense vector spaces.",
            "source_type": "upload",
            "privacy_tier": "public"
        })
        await client.post("/api/v1/documents/text", json={
            "title": "Private Research Diary",
            "content": "Experiment notes on RRF weighting and scoring parameters.",
            "source_type": "note",
            "privacy_tier": "private"
        })

        summary_resp = await client.get("/api/v1/knowledge/summary")
        assert summary_resp.status_code == 200
        summary = summary_resp.json()
        assert summary["total_documents"] >= 2
        assert "privacy_tiers" in summary
        assert "public" in summary["privacy_tiers"]
        assert "private" in summary["privacy_tiers"]
        assert "sensitive" in summary["privacy_tiers"]
        assert summary["privacy_tiers"]["public"]["document_count"] >= 1
        assert summary["privacy_tiers"]["private"]["document_count"] >= 1
        assert "sources" in summary
        assert len(summary["sources"]) >= 4
