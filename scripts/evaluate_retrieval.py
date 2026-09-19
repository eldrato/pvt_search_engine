#!/usr/bin/env python3
"""
Aegis Information Retrieval Benchmark Suite

Executes automated evaluation comparing Lexical (BM25), Semantic (Dense Vectors),
and Hybrid (Reciprocal Rank Fusion) across Precision@K, Recall@K, MRR, and NDCG@K.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add backend to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "packages" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import get_sessionmaker, init_db
from app.services.search import search_service
from app.evaluation.retrieval_benchmark import retrieval_benchmark


async def main():
    print("================================================================================")
    print("           AEGIS AUTOMATED RETRIEVAL EVALUATION BENCHMARK SUITE")
    print("================================================================================")

    await init_db()
    sm = get_sessionmaker()

    async with sm() as session:
        report = await retrieval_benchmark.evaluate_engine(
            search_fn=search_service.search,
            modes=["lexical", "semantic", "hybrid"],
            db=session
        )

    modes_data = report.get("modes", {})

    print(f"\nEvaluated Cases: {report.get('evaluated_cases')} queries")
    print("-" * 80)
    print(f"{'Metric':<18} | {'Lexical (BM25)':<16} | {'Semantic (Vector)':<18} | {'Hybrid (RRF)':<16}")
    print("-" * 80)

    metrics = [
        ("Precision@1", "mean_p@1"),
        ("Precision@3", "mean_p@3"),
        ("Precision@5", "mean_p@5"),
        ("Recall@5", "mean_recall@5"),
        ("MRR", "mean_mrr"),
        ("NDCG@5", "mean_ndcg@5"),
        ("Avg Latency (ms)", "mean_latency_ms"),
    ]

    for label, key in metrics:
        lex_val = modes_data.get("lexical", {}).get(key, 0.0)
        sem_val = modes_data.get("semantic", {}).get(key, 0.0)
        hyb_val = modes_data.get("hybrid", {}).get(key, 0.0)
        print(f"{label:<18} | {lex_val:<16} | {sem_val:<18} | {hyb_val:<16}")

    print("-" * 80)
    print("\nBenchmark completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
