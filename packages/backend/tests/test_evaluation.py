import pytest
import httpx
from app.evaluation.retrieval_benchmark import (
    compute_precision_at_k,
    compute_recall_at_k,
    compute_mrr,
    compute_ndcg_at_k,
    RetrievalBenchmark,
    BENCHMARK_CASES
)
from app.main import app
from app.core.db import init_db


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()


def test_metric_precision_at_k():
    retrieved = ["doc1", "doc2", "doc3", "doc4", "doc5"]
    relevant = {"doc1", "doc3"}

    assert compute_precision_at_k(retrieved, relevant, k=1) == 1.0
    assert compute_precision_at_k(retrieved, relevant, k=2) == 0.5
    assert compute_precision_at_k(retrieved, relevant, k=3) == 0.6667
    assert compute_precision_at_k(retrieved, relevant, k=5) == 0.4
    assert compute_precision_at_k([], relevant, k=5) == 0.0
    assert compute_precision_at_k(retrieved, set(), k=5) == 0.0


def test_metric_recall_at_k():
    retrieved = ["doc1", "doc2", "doc3", "doc4", "doc5"]
    relevant = {"doc1", "doc3", "doc8", "doc9"}

    assert compute_recall_at_k(retrieved, relevant, k=1) == 0.25
    assert compute_recall_at_k(retrieved, relevant, k=3) == 0.50
    assert compute_recall_at_k(retrieved, relevant, k=5) == 0.50
    assert compute_recall_at_k([], relevant, k=5) == 0.0
    assert compute_recall_at_k(retrieved, set(), k=5) == 0.0


def test_metric_mrr():
    # Relevant item at rank 1
    assert compute_mrr(["doc1", "doc2", "doc3"], {"doc1"}) == 1.0
    # Relevant item at rank 2
    assert compute_mrr(["doc1", "doc2", "doc3"], {"doc2"}) == 0.5
    # Relevant item at rank 3
    assert compute_mrr(["doc1", "doc2", "doc3"], {"doc3"}) == 0.3333
    # No relevant items found
    assert compute_mrr(["doc1", "doc2", "doc3"], {"doc9"}) == 0.0
    # Empty retrieved list
    assert compute_mrr([], {"doc1"}) == 0.0


def test_metric_ndcg_at_k():
    # Perfect ranking: highest grade first
    grades = {"doc1": 3.0, "doc2": 2.0, "doc3": 1.0}
    perfect_retrieved = ["doc1", "doc2", "doc3"]
    assert compute_ndcg_at_k(perfect_retrieved, grades, k=3) == 1.0

    # Inverted ranking: lowest grade first
    inverted_retrieved = ["doc3", "doc2", "doc1"]
    ndcg_inverted = compute_ndcg_at_k(inverted_retrieved, grades, k=3)
    assert ndcg_inverted < 1.0
    assert ndcg_inverted > 0.5

    # Completely irrelevant retrieved
    assert compute_ndcg_at_k(["docX", "docY"], grades, k=2) == 0.0


@pytest.mark.asyncio
async def test_retrieval_benchmark_runner():
    benchmark = RetrievalBenchmark()

    async def mock_search(query: str, mode: str = "hybrid", limit: int = 10, db=None):
        # Return mock results relevant to the query
        return {
            "query": query,
            "total": 2,
            "results": [
                {
                    "chunk_id": "c1",
                    "title": "Architecture Specification",
                    "content": "Aegis single source of truth SSOT and relational database persistence",
                    "score": 3.5
                },
                {
                    "chunk_id": "c2",
                    "title": "Crawling Guide",
                    "content": "Controlled web crawler allowlist and robots txt enforcement",
                    "score": 2.1
                }
            ]
        }

    report = await benchmark.evaluate_engine(
        search_fn=mock_search,
        modes=["lexical", "hybrid"]
    )

    assert "benchmark_version" in report
    assert report["evaluated_cases"] == len(BENCHMARK_CASES)
    assert "lexical" in report["modes"]
    assert "hybrid" in report["modes"]

    lex_mode = report["modes"]["lexical"]
    assert "mean_p@1" in lex_mode
    assert "mean_mrr" in lex_mode
    assert "mean_ndcg@5" in lex_mode
    assert len(lex_mode["query_details"]) == len(BENCHMARK_CASES)


@pytest.mark.asyncio
async def test_evaluation_api_endpoint():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/evaluation/benchmark?modes=hybrid")
        assert resp.status_code == 200
        data = resp.json()
        assert "benchmark_version" in data
        assert "modes" in data
        assert "hybrid" in data["modes"]
