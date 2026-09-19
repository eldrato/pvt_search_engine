import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete
from app.main import app
from app.models.document import Document
from app.core.db import init_db, get_sessionmaker


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(delete(Document))
        await session.commit()


@pytest.mark.asyncio
async def test_text_ingestion_and_search_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Ingest a note
        note_payload = {
            "title": "Quantum Computing Principles",
            "content": "Quantum entanglement and superposition allow quantum computers to solve certain cryptographic problems exponentially faster than classical computers.",
            "source_type": "note",
            "metadata": {"subject": "physics"}
        }

        resp = await client.post("/api/v1/documents/text", json=note_payload)
        assert resp.status_code == 201
        data = resp.json()
        assert "document" in data
        assert data["chunks_created"] >= 1
        doc_id = data["document"]["id"]

        # 2. List documents
        list_resp = await client.get("/api/v1/documents")
        assert list_resp.status_code == 200
        docs_data = list_resp.json()
        assert docs_data["total"] >= 1
        assert any(d["id"] == doc_id for d in docs_data["documents"])

        # 3. Search for keyword "superposition"
        search_resp = await client.get("/api/v1/search?q=superposition")
        assert search_resp.status_code == 200
        search_data = search_resp.json()
        assert search_data["total"] >= 1
        assert len(search_data["results"]) >= 1

        top_hit = search_data["results"][0]
        assert top_hit["document_id"] == doc_id
        assert "Quantum Computing" in top_hit["title"]
        assert "<mark" in top_hit["snippet"]
        assert "superposition" in top_hit["snippet"].lower()
        assert top_hit["score"] > 0

        # 4. Get document details
        detail_resp = await client.get(f"/api/v1/documents/{doc_id}")
        assert detail_resp.status_code == 200
        detail_data = detail_resp.json()
        assert detail_data["id"] == doc_id
        assert len(detail_data["chunks"]) >= 1

        # 5. Delete document
        del_resp = await client.delete(f"/api/v1/documents/{doc_id}")
        assert del_resp.status_code == 200

        # 6. Verify deletion
        list_resp2 = await client.get("/api/v1/documents")
        assert not any(d["id"] == doc_id for d in list_resp2.json()["documents"])


@pytest.mark.asyncio
async def test_file_upload_ingestion():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        file_content = b"""# Hybrid Retrieval Architecture

Aegis combines BM25 keyword inverted indexing with dense vector embeddings.
Reciprocal Rank Fusion (RRF) harmonizes both rankings.
"""
        files = {"file": ("architecture.md", file_content, "text/markdown")}
        resp = await client.post("/api/v1/documents/upload", files=files, data={"source_type": "upload"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["document"]["title"] == "Hybrid Retrieval Architecture"
        assert data["chunks_created"] >= 1
        doc_id = data["document"]["id"]

        # Search for "Reciprocal Rank Fusion"
        search_resp = await client.get("/api/v1/search?q=Fusion")
        assert search_resp.status_code == 200
        results = search_resp.json()["results"]
        assert any("Fusion" in r["snippet"] or "Fusion" in r["title"] for r in results)

        # Cleanup
        await client.delete(f"/api/v1/documents/{doc_id}")
