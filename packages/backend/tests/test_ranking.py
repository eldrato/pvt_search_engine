import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

from app.main import app
from app.models.document import Document
from app.core.db import init_db, get_sessionmaker
from app.ranking.scorer import ranking_scorer, RankingScorer


def test_title_boost_calculation():
    scorer = RankingScorer()
    query = "quantum computing"

    # Exact query in title
    boost_exact, reason_exact = scorer.compute_title_boost(
        query=query,
        title="Introduction to Quantum Computing",
        anchor_label=None
    )
    assert boost_exact >= 1.50
    assert "Exact query matches" in reason_exact

    # All terms in title but non-contiguous
    boost_terms, reason_terms = scorer.compute_title_boost(
        query=query,
        title="Computing Systems using Quantum",
        anchor_label=None
    )
    assert boost_terms >= 1.30

    # No title match, but anchor match
    boost_anchor, reason_anchor = scorer.compute_title_boost(
        query=query,
        title="General Architecture",
        anchor_label="Quantum Computing Overview"
    )
    assert boost_anchor >= 1.10
    assert "Anchor label matches" in reason_anchor

    # Neither matches
    boost_none, reason_none = scorer.compute_title_boost(
        query=query,
        title="Database Systems",
        anchor_label="Section 1"
    )
    assert boost_none == 1.00


def test_authority_boost_hierarchy():
    scorer = RankingScorer()

    boost_note, _ = scorer.compute_authority_boost("note")
    boost_upload, _ = scorer.compute_authority_boost("upload")
    boost_code, _ = scorer.compute_authority_boost("code")
    boost_web, _ = scorer.compute_authority_boost("web")
    boost_web_docs, _ = scorer.compute_authority_boost("web", {"domain": "docs.python.org"})

    # Hierarchy: Note > Upload > Code > Curated Web > Generic Web
    assert boost_note == 1.30
    assert boost_upload == 1.20
    assert boost_code == 1.15
    assert boost_web_docs == 1.10
    assert boost_web == 1.00
    assert boost_note > boost_upload > boost_code > boost_web


def test_freshness_decay():
    scorer = RankingScorer()
    now = datetime.now(timezone.utc)

    # 1. Created right now (0 days old)
    boost_0, reason_0 = scorer.compute_freshness_boost(now)
    assert boost_0 >= 0.99
    assert "today" in reason_0

    # 2. Exactly 90 days old (one half-life)
    t_90 = now - timedelta(days=90)
    boost_90, _ = scorer.compute_freshness_boost(t_90)
    # Expected: 0.50 + 0.50 * 0.5 = 0.75
    assert 0.73 <= boost_90 <= 0.77

    # 3. 365 days old (~1 year)
    t_365 = now - timedelta(days=365)
    boost_365, _ = scorer.compute_freshness_boost(t_365)
    # Never drops below evergreen floor of 0.50
    assert boost_365 >= 0.50
    assert boost_365 < boost_90

    # 4. None / missing timestamp fallback
    boost_none, _ = scorer.compute_freshness_boost(None)
    assert boost_none == 0.90


def test_phrase_proximity_boost():
    scorer = RankingScorer()

    # Exact phrase
    boost_exact, reason_exact = scorer.compute_phrase_boost(
        query="distributed consensus algorithm",
        content="The Raft distributed consensus algorithm ensures replicated state machine safety."
    )
    assert boost_exact == 1.25
    assert "Exact contiguous phrase match" in reason_exact

    # Close proximity (< 15 words)
    boost_prox, reason_prox = scorer.compute_phrase_boost(
        query="distributed consensus",
        content="A modern distributed fault-tolerant protocol providing reliable consensus across nodes."
    )
    assert boost_prox == 1.10
    assert "High term proximity" in reason_prox

    # Scattered terms
    boost_scattered, _ = scorer.compute_phrase_boost(
        query="distributed consensus",
        content="Distributed systems require many architectural considerations. In early chapters we study networking, operating systems, and disk storage. Later in chapter twenty we examine reaching consensus among nodes."
    )
    assert boost_scattered == 1.00

    # Single term query
    boost_single, _ = scorer.compute_phrase_boost(
        query="distributed",
        content="Distributed systems are scalable."
    )
    assert boost_single == 1.00


def test_rerank_composite_scoring():
    scorer = RankingScorer()
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=200)

    hits = [
        {
            "chunk_id": "c1",
            "title": "Random Web Page",
            "content": "Some discussion about machine learning pipelines and models.",
            "source_type": "web",
            "score": 3.0,  # higher initial BM25
            "created_at": old_date.isoformat()
        },
        {
            "chunk_id": "c2",
            "title": "Machine Learning Pipelines",  # Exact title match
            "content": "My personal machine learning pipelines notes and setup.",
            "source_type": "note",  # 1.3x note authority
            "score": 2.2,  # slightly lower initial BM25
            "created_at": now.isoformat()  # fresh
        }
    ]

    reranked = scorer.rerank("machine learning pipelines", hits)
    # c2 should surpass c1 due to title match (1.5x) + note authority (1.3x) + freshness (1.0x) + phrase match (1.25x)
    assert reranked[0]["chunk_id"] == "c2"
    assert reranked[1]["chunk_id"] == "c1"

    top_breakdown = reranked[0]["score_breakdown"]
    assert top_breakdown["title_boost"] >= 1.50
    assert top_breakdown["authority_boost"] == 1.30
    assert top_breakdown["freshness_boost"] >= 0.99
    assert len(top_breakdown["explanation"]) >= 4


@pytest.mark.asyncio
async def test_search_api_returns_score_breakdown():
    await init_db()
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(delete(Document))
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Ingest note
        payload = {
            "title": "Aegis Ranking Engine",
            "content": "The multi-signal ranking function combines lexical BM25 with authority, freshness decay, and phrase proximity.",
            "source_type": "note"
        }
        res = await client.post("/api/v1/documents/text", json=payload)
        assert res.status_code == 201

        # Search
        search_res = await client.get("/api/v1/search?q=ranking+engine")
        assert search_res.status_code == 200
        data = search_res.json()
        assert data["total"] >= 1
        top_result = data["results"][0]

        # Verify score_breakdown exists and is well-formed
        assert "score_breakdown" in top_result
        breakdown = top_result["score_breakdown"]
        assert breakdown is not None
        assert "base_bm25" in breakdown
        assert "title_boost" in breakdown
        assert "authority_boost" in breakdown
        assert "freshness_boost" in breakdown
        assert "phrase_boost" in breakdown
        assert "final_score" in breakdown
        assert "explanation" in breakdown
        assert len(breakdown["explanation"]) > 0
        assert breakdown["final_score"] == top_result["score"]
