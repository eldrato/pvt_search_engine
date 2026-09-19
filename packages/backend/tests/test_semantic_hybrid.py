import pytest
import numpy as np
from app.services.embedding import EmbeddingService, embedding_service
from app.services.qdrant import QdrantService
from app.services.search import SearchService
from app.ranking.scorer import RankingScorer


def test_embedding_service_dimension():
    vec = embedding_service.embed_query("Aegis private personal search engine")
    assert isinstance(vec, list)
    assert len(vec) == 384
    # Ensure vector is normalized (L2 norm approx 1.0)
    norm = np.linalg.norm(vec)
    assert abs(norm - 1.0) < 1e-3


def test_embedding_semantic_similarity():
    s1 = embedding_service.embed_query("PostgreSQL relational database management system")
    s2 = embedding_service.embed_query("SQL database data storage engine")
    s3 = embedding_service.embed_query("Chocolate chip cookie baking recipe with flour and sugar")

    # Cosine similarity is dot product of normalized vectors
    sim_related = np.dot(s1, s2)
    sim_unrelated = np.dot(s1, s3)

    assert sim_related > sim_unrelated, f"Expected related ({sim_related:.3f}) > unrelated ({sim_unrelated:.3f})"


def test_embedding_fallback_deterministic():
    svc = EmbeddingService()
    v1 = svc._fallback_embed("offline machine without network access")
    v2 = svc._fallback_embed("offline machine without network access")
    v3 = svc._fallback_embed("completely different phrase")

    assert len(v1) == 384
    assert v1 == v2  # 100% deterministic
    sim = np.dot(v1, v3)
    assert sim < 0.95


def test_qdrant_in_memory_service():
    qdrant = QdrantService(storage_path=":memory:")
    # Force in-memory client
    from qdrant_client import QdrantClient
    qdrant.client = QdrantClient(location=":memory:")
    qdrant.init_collection()

    payloads = [
        {
            "chunk_id": "chunk_doc1_0",
            "document_id": "doc_1",
            "title": "Aegis Architecture",
            "content": "Single source of truth architecture using Postgres and Qdrant",
            "source_type": "note",
            "anchor_label": "Section 1",
            "chunk_index": 0
        },
        {
            "chunk_id": "chunk_doc2_0",
            "document_id": "doc_2",
            "title": "Cooking Recipes",
            "content": "Baking delicious Italian sourdough bread and pastries",
            "source_type": "upload",
            "anchor_label": "Recipe 1",
            "chunk_index": 0
        }
    ]

    v1 = embedding_service.embed_query(payloads[0]["content"])
    v2 = embedding_service.embed_query(payloads[1]["content"])
    count = qdrant.upsert_chunks(payloads, [v1, v2])
    assert count == 2

    # Query for database architecture
    q_vec = embedding_service.embed_query("Postgres relational storage SSOT")
    hits = qdrant.search_vectors(q_vec, limit=2)
    assert len(hits) == 2
    assert hits[0]["title"] == "Aegis Architecture"
    assert hits[0]["semantic_score"] > hits[1]["semantic_score"]

    # Test filtering by source_type
    filtered_hits = qdrant.search_vectors(q_vec, source_type="upload", limit=2)
    assert len(filtered_hits) == 1
    assert filtered_hits[0]["source_type"] == "upload"


def test_rrf_fusion_mathematics():
    searcher = SearchService()

    lexical_hits = [
        {"chunk_id": "c1", "title": "Doc A", "score": 10.0, "source_type": "note"},
        {"chunk_id": "c2", "title": "Doc B", "score": 5.0, "source_type": "upload"}
    ]
    semantic_hits = [
        {"chunk_id": "c2", "title": "Doc B", "score": 0.90, "semantic_score": 0.90, "source_type": "upload"},
        {"chunk_id": "c3", "title": "Doc C", "score": 0.85, "semantic_score": 0.85, "source_type": "code"}
    ]

    fused = searcher._fuse_rrf(lexical_hits, semantic_hits)
    assert len(fused) == 3

    # c2 appeared in BOTH:
    # rank_lex = 2, rank_vec = 1
    # rrf = 1/(60+2) + 1/(60+1) = 1/62 + 1/61 = 0.016129 + 0.016393 = 0.032522
    c2 = next(h for h in fused if h["chunk_id"] == "c2")
    assert c2["lexical_rank"] == 2
    assert c2["semantic_rank"] == 1
    assert abs(c2["rrf_score"] - (1/62 + 1/61)) < 1e-5

    # c1 appeared only in lexical: rank_lex = 1
    c1 = next(h for h in fused if h["chunk_id"] == "c1")
    assert c1["lexical_rank"] == 1
    assert c1["semantic_rank"] is None
    assert abs(c1["rrf_score"] - (1/61)) < 1e-5

    # Because c2 appeared in both, its fused RRF score should rank highest!
    assert fused[0]["chunk_id"] == "c2"


@pytest.mark.asyncio
async def test_search_service_modes():
    searcher = SearchService()

    # Empty query test
    res = await searcher.search("")
    assert res["total"] == 0
    assert res["engine"] == "none"

    # Query with mock database lexical & semantic
    res_hybrid = await searcher.search("test query", mode="hybrid")
    assert "results" in res_hybrid
    assert res_hybrid["engine"] == "hybrid_rrf_multi_signal"

    res_lex = await searcher.search("test query", mode="lexical")
    assert "results" in res_lex

    res_sem = await searcher.search("test query", mode="semantic")
    assert "results" in res_sem
