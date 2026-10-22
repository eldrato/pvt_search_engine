import os
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete
from app.main import app
from app.models.document import Document, DocumentChunk
from app.models.graph import Entity, Relationship, EntityGrounding
from app.core.db import init_db, get_sessionmaker
from app.services.ingestion import ingestion_service
from app.services.knowledge_graph import knowledge_graph_service

os.environ["AEGIS_OFFLINE_EMBEDDER"] = "true"


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(delete(EntityGrounding))
        await session.execute(delete(Relationship))
        await session.execute(delete(Entity))
        await session.execute(delete(DocumentChunk))
        await session.execute(delete(Document))
        await session.commit()


def test_span_and_relationship_extraction_unit():
    """Unit test for regex/lexicon extraction logic and span offsets."""
    text = "FastAPI uses PostgreSQL and connects to OpenSearch for fast lexical search."
    spans = knowledge_graph_service.extract_spans_from_text(text)
    
    names = [s["name"] for s in spans]
    assert "FastAPI" in names
    assert "PostgreSQL" in names
    assert "OpenSearch" in names
    assert "Lexical Search" in names

    # Check offsets
    for s in spans:
        extracted_substr = text[s["span_start"]:s["span_end"]]
        assert extracted_substr.lower() == s["matched_text"].lower()

    # Check relationship extraction
    rels = knowledge_graph_service.extract_relationships_from_text(text, spans)
    assert len(rels) >= 1
    rel_types = [r["relation_type"] for r in rels]
    assert "USES" in rel_types or "ASSOCIATED_WITH" in rel_types


@pytest.mark.asyncio
async def test_end_to_end_knowledge_graph_flow():
    """Test full document ingestion -> auto extraction -> graph queries & provenance grounding."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sm = get_sessionmaker()

        # 1. Ingest a document containing rich concepts and technologies
        doc_text = (
            "Aegis Engine uses FastAPI and PostgreSQL for resilient metadata storage. "
            "It integrates with Qdrant for semantic search and OpenSearch for BM25 scoring. "
            "Reciprocal Rank Fusion fuses lexical and dense vector scores."
        )

        async with sm() as session:
            ingest_res = await ingestion_service.ingest_text(
                title="Aegis Architecture Guide",
                text=doc_text,
                source_type="upload",
                privacy_tier="public",
                db=session
            )
            doc_id = ingest_res["document"]["id"]

        # 2. Verify graph topology endpoint
        graph_resp = await client.get("/api/v1/graph")
        assert graph_resp.status_code == 200
        graph_data = graph_resp.json()
        assert len(graph_data["nodes"]) >= 4
        assert len(graph_data["edges"]) >= 2

        node_names = [n["name"] for n in graph_data["nodes"]]
        assert "FastAPI" in node_names
        assert "PostgreSQL" in node_names
        assert "Qdrant" in node_names
        assert "OpenSearch" in node_names

        # 3. Verify graph stats
        stats_resp = await client.get("/api/v1/graph/stats")
        assert stats_resp.status_code == 200
        stats = stats_resp.json()
        assert stats["total_nodes"] >= 4
        assert stats["total_edges"] >= 2
        assert stats["total_groundings"] >= 4
        assert "TECHNOLOGY" in stats["entity_types"]

        # 4. Search entities
        search_ent_resp = await client.get("/api/v1/graph/search?query=FastAPI")
        assert search_ent_resp.status_code == 200
        found_entities = search_ent_resp.json()
        assert len(found_entities) >= 1
        fastapi_entity = found_entities[0]
        assert fastapi_entity["name"] == "FastAPI"

        # 5. Entity details & source grounding provenance
        entity_id = fastapi_entity["id"]
        detail_resp = await client.get(f"/api/v1/graph/entity/{entity_id}")
        assert detail_resp.status_code == 200
        details = detail_resp.json()
        assert details["name"] == "FastAPI"
        assert len(details["relationships"]) >= 1
        assert len(details["citations"]) >= 1

        # Check provenance citation fields
        citation = details["citations"][0]
        assert citation["document_title"] == "Aegis Architecture Guide"
        assert "span_start" in citation
        assert "span_end" in citation
        assert "matched_text" in citation
        assert "context_snippet" in citation
        assert citation["document_id"] == doc_id

        # 6. Test ego-subgraph
        subgraph_resp = await client.get(f"/api/v1/graph/subgraph?entity_id={entity_id}&depth=1")
        assert subgraph_resp.status_code == 200
        subgraph = subgraph_resp.json()
        assert subgraph["center_node_id"] == entity_id
        assert len(subgraph["nodes"]) >= 2

        # 7. Test re-extraction endpoint
        extract_resp = await client.post(f"/api/v1/graph/extract/{doc_id}")
        assert extract_resp.status_code == 200
        extract_data = extract_resp.json()
        assert extract_data["document_id"] == doc_id
        assert extract_data["entities_found"] >= 4

        # 8. Test Search API returning knowledge graph entities
        search_api_resp = await client.get("/api/v1/search?q=FastAPI&mode=lexical")
        assert search_api_resp.status_code == 200
        search_res = search_api_resp.json()
        assert "knowledge_entities" in search_res
        assert any(e["name"] == "FastAPI" for e in search_res["knowledge_entities"])

        # 9. Test entity deletion cascade
        del_resp = await client.delete(f"/api/v1/graph/entity/{entity_id}")
        assert del_resp.status_code == 200

        # Verify entity is gone
        del_check = await client.get(f"/api/v1/graph/entity/{entity_id}")
        assert del_check.status_code == 404
