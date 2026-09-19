import math
import time
from typing import List, Dict, Any, Set, Optional


def compute_precision_at_k(retrieved: List[str], relevant: Set[str], k: int = 5) -> float:
    """
    Computes Precision@K: Fraction of top-k retrieved items that are relevant.
    """
    if k <= 0 or not retrieved:
        return 0.0
    top_k = retrieved[:k]
    hits = sum(1 for item in top_k if item in relevant)
    return round(hits / float(k), 4)


def compute_recall_at_k(retrieved: List[str], relevant: Set[str], k: int = 5) -> float:
    """
    Computes Recall@K: Fraction of all relevant items captured in top-k.
    """
    if not relevant or k <= 0 or not retrieved:
        return 0.0
    top_k = retrieved[:k]
    hits = sum(1 for item in top_k if item in relevant)
    return round(hits / float(len(relevant)), 4)


def compute_mrr(retrieved: List[str], relevant: Set[str]) -> float:
    """
    Computes Mean Reciprocal Rank (MRR): 1 / rank of the first relevant retrieved item.
    """
    if not relevant or not retrieved:
        return 0.0
    for rank, item in enumerate(retrieved, start=1):
        if item in relevant:
            return round(1.0 / rank, 4)
    return 0.0


def compute_ndcg_at_k(retrieved: List[str], relevance_grades: Dict[str, float], k: int = 5) -> float:
    """
    Computes Normalized Discounted Cumulative Gain (NDCG@K).
    DCG = sum_{i=1}^k (2^{rel_i} - 1) / log2(i + 1)
    """
    if k <= 0 or not retrieved:
        return 0.0

    # Calculate actual DCG
    dcg = 0.0
    for i, item in enumerate(retrieved[:k], start=1):
        rel = relevance_grades.get(item, 0.0)
        dcg += (math.pow(2, rel) - 1.0) / math.log2(i + 1)

    # Calculate ideal DCG (IDCG)
    all_grades = sorted(relevance_grades.values(), reverse=True)[:k]
    idcg = 0.0
    for i, rel in enumerate(all_grades, start=1):
        idcg += (math.pow(2, rel) - 1.0) / math.log2(i + 1)

    if idcg <= 1e-9:
        return 1.0 if dcg <= 1e-9 else 0.0

    return round(dcg / idcg, 4)


# Reference queries with gold-standard relevance criteria (title keyword / semantic substring)
BENCHMARK_CASES = [
    {
        "id": "case_1_ssot_architecture",
        "query": "PostgreSQL Single Source of Truth SSOT architecture",
        "category": "keyword_precision",
        "match_criterion": lambda doc_title, content: (
            "source of truth" in content.lower() or "ssot" in content.lower() or "architecture" in doc_title.lower()
        ),
        "ideal_relevance": 3.0
    },
    {
        "id": "case_2_semantic_persistence",
        "query": "local relational data storage and resilient offline fallbacks",
        "category": "semantic_paraphrase",
        "match_criterion": lambda doc_title, content: (
            "sqlite" in content.lower() or "database" in content.lower() or "storage" in content.lower()
        ),
        "ideal_relevance": 3.0
    },
    {
        "id": "case_3_vector_embeddings",
        "query": "dense vector embeddings approximate nearest neighbor search",
        "category": "hybrid_conceptual",
        "match_criterion": lambda doc_title, content: (
            "vector" in content.lower() or "embedding" in content.lower() or "qdrant" in content.lower()
        ),
        "ideal_relevance": 3.0
    },
    {
        "id": "case_4_crawler_frontier",
        "query": "allowlist domain web crawler robots txt rate limits",
        "category": "keyword_precision",
        "match_criterion": lambda doc_title, content: (
            "crawler" in content.lower() or "allowlist" in content.lower() or "robots" in content.lower()
        ),
        "ideal_relevance": 3.0
    }
]


class RetrievalBenchmark:
    """
    Automated evaluation harness comparing Lexical, Semantic, and Hybrid RRF retrieval.
    """

    async def evaluate_engine(
        self,
        search_fn,
        modes: Optional[List[str]] = None,
        db=None
    ) -> Dict[str, Any]:
        modes = modes or ["lexical", "semantic", "hybrid"]
        results_by_mode: Dict[str, Any] = {}

        for mode in modes:
            latencies = []
            p1_list, p3_list, p5_list = [], [], []
            recall_list = []
            mrr_list = []
            ndcg_list = []

            query_details = []

            for case in BENCHMARK_CASES:
                query = case["query"]
                criterion = case["match_criterion"]

                t0 = time.perf_counter()
                search_res = await search_fn(query=query, mode=mode, limit=10, db=db)
                latency_ms = (time.perf_counter() - t0) * 1000.0
                latencies.append(latency_ms)

                hits = search_res.get("results", [])

                # Determine which retrieved hits meet the gold-standard relevance criteria
                retrieved_identifiers = []
                relevant_set = set()
                relevance_grades = {}

                for idx, hit in enumerate(hits):
                    cid = hit.get("chunk_id") or str(idx)
                    retrieved_identifiers.append(cid)
                    is_rel = criterion(hit.get("title", ""), hit.get("content", ""))
                    if is_rel:
                        relevant_set.add(cid)
                        relevance_grades[cid] = 3.0  # high relevance
                    else:
                        relevance_grades[cid] = 0.0

                p1 = compute_precision_at_k(retrieved_identifiers, relevant_set, k=1)
                p3 = compute_precision_at_k(retrieved_identifiers, relevant_set, k=3)
                p5 = compute_precision_at_k(retrieved_identifiers, relevant_set, k=5)
                rec = compute_recall_at_k(retrieved_identifiers, relevant_set, k=5)
                mrr = compute_mrr(retrieved_identifiers, relevant_set)
                ndcg = compute_ndcg_at_k(retrieved_identifiers, relevance_grades, k=5)

                p1_list.append(p1)
                p3_list.append(p3)
                p5_list.append(p5)
                recall_list.append(rec)
                mrr_list.append(mrr)
                ndcg_list.append(ndcg)

                query_details.append({
                    "case_id": case["id"],
                    "query": query,
                    "category": case["category"],
                    "retrieved_count": len(hits),
                    "relevant_found": len(relevant_set),
                    "p@1": p1,
                    "p@5": p5,
                    "mrr": mrr,
                    "ndcg@5": ndcg,
                    "latency_ms": round(latency_ms, 2)
                })

            n = max(1, len(BENCHMARK_CASES))
            results_by_mode[mode] = {
                "mean_latency_ms": round(sum(latencies) / n, 2),
                "mean_p@1": round(sum(p1_list) / n, 4),
                "mean_p@3": round(sum(p3_list) / n, 4),
                "mean_p@5": round(sum(p5_list) / n, 4),
                "mean_recall@5": round(sum(recall_list) / n, 4),
                "mean_mrr": round(sum(mrr_list) / n, 4),
                "mean_ndcg@5": round(sum(ndcg_list) / n, 4),
                "query_details": query_details
            }

        return {
            "benchmark_version": "1.0.0",
            "evaluated_cases": len(BENCHMARK_CASES),
            "modes": results_by_mode,
            "timestamp": time.time()
        }


retrieval_benchmark = RetrievalBenchmark()
