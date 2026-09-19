import re
import time
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.models.document import Document, DocumentChunk
from app.services.opensearch import opensearch_service
from app.services.embedding import embedding_service
from app.services.qdrant import qdrant_service
from app.ranking.scorer import ranking_scorer
from app.core.logging import logger

RRF_K = 60.0
WEIGHT_LEXICAL = 1.0
WEIGHT_SEMANTIC = 1.0


class SearchService:
    """
    Unified Search Engine supporting:
    - Hybrid Fusion: Reciprocal Rank Fusion (RRF) of BM25 + Dense Vectors + Multi-Signal Ranking
    - Lexical: OpenSearch BM25 with Database Lexical Fallback
    - Semantic: FastEmbed ONNX local dense embeddings with Qdrant ANN cosine retrieval
    """

    async def search(
        self,
        query: str,
        mode: str = "hybrid",
        source_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        query = query.strip()
        if not query:
            return {
                "query": "",
                "total": 0,
                "latency_ms": 0.0,
                "engine": "none",
                "results": []
            }

        start_time = time.perf_counter()
        mode = (mode or "hybrid").lower()
        candidate_limit = max(limit * 3, 50)

        if mode == "lexical":
            candidates, engine_name = await self._search_lexical(
                query=query,
                source_type=source_type,
                limit=candidate_limit,
                db=db
            )
            # Mark lexical ranks
            for idx, c in enumerate(candidates):
                c["lexical_rank"] = idx + 1
            reranked = ranking_scorer.rerank(query, candidates)
            engine = f"{engine_name}_multi_signal"

        elif mode == "semantic":
            candidates = await self._search_semantic(
                query=query,
                source_type=source_type,
                limit=candidate_limit
            )
            # Mark semantic ranks
            for idx, c in enumerate(candidates):
                c["semantic_rank"] = idx + 1
            reranked = ranking_scorer.rerank(query, candidates)
            engine = "qdrant_vector_multi_signal"

        else:  # "hybrid" (default)
            lexical_hits, _ = await self._search_lexical(
                query=query,
                source_type=source_type,
                limit=candidate_limit,
                db=db
            )
            semantic_hits = await self._search_semantic(
                query=query,
                source_type=source_type,
                limit=candidate_limit
            )

            # Apply Reciprocal Rank Fusion
            fused_candidates = self._fuse_rrf(lexical_hits, semantic_hits)
            reranked = ranking_scorer.rerank(query, fused_candidates)
            engine = "hybrid_rrf_multi_signal"

        paginated = reranked[offset : offset + limit]
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return {
            "query": query,
            "total": len(reranked),
            "latency_ms": duration_ms,
            "engine": engine,
            "results": paginated
        }

    async def _search_lexical(
        self,
        query: str,
        source_type: Optional[str] = None,
        limit: int = 50,
        db: Optional[AsyncSession] = None
    ) -> tuple[List[Dict[str, Any]], str]:
        """Performs lexical search via OpenSearch BM25 or DB SQL fallback."""
        if opensearch_service.is_connected():
            os_result = opensearch_service.search(
                query_text=query,
                source_type=source_type,
                limit=limit,
                offset=0
            )
            if os_result is not None:
                return os_result.get("results", []), "opensearch_bm25"

        # Database Lexical Fallback
        if not db:
            return [], "no_active_database"

        terms = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 1]
        if not terms:
            terms = [query.lower()]

        filters = []
        for term in terms:
            pattern = f"%{term}%"
            filters.append(DocumentChunk.content.ilike(pattern))
            filters.append(Document.title.ilike(pattern))

        stmt = (
            select(DocumentChunk, Document)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(or_(*filters))
        )
        if source_type:
            stmt = stmt.where(Document.source_type == source_type)

        res = await db.execute(stmt)
        rows = res.all()

        scored_results = []
        for chunk, doc in rows:
            content_lower = chunk.content.lower()
            title_lower = doc.title.lower()

            score = 0.0
            for term in terms:
                title_matches = title_lower.count(term)
                content_matches = content_lower.count(term)
                score += (title_matches * 3.0) + (content_matches * 1.0)

            snippet = self._generate_highlighted_snippet(chunk.content, terms)
            loc_meta = chunk.location_meta or {}
            anchor_label = loc_meta.get("anchor_label", f"Chunk #{chunk.chunk_index + 1}")

            scored_results.append({
                "chunk_id": chunk.id,
                "document_id": doc.id,
                "title": doc.title,
                "snippet": snippet,
                "content": chunk.content,
                "score": round(max(0.5, score), 3),
                "source_type": doc.source_type,
                "mime_type": doc.mime_type,
                "anchor_label": anchor_label,
                "chunk_index": chunk.chunk_index,
                "location_meta": loc_meta,
                "created_at": doc.created_at.isoformat() if doc.created_at else None
            })

        # Sort raw results by lexical score descending
        scored_results.sort(key=lambda x: x["score"], reverse=True)
        return scored_results[:limit], "database_lexical"

    async def _search_semantic(
        self,
        query: str,
        source_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Performs dense vector retrieval via local FastEmbed + Qdrant."""
        if not qdrant_service.is_connected():
            return []

        query_vec = embedding_service.embed_query(query)
        hits = qdrant_service.search_vectors(
            query_vector=query_vec,
            source_type=source_type,
            limit=limit
        )

        terms = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 1]
        for hit in hits:
            # Generate snippet with keyword highlights if any query terms appear
            if terms and "snippet" in hit and not hit["snippet"].startswith("<mark"):
                hit["snippet"] = self._generate_highlighted_snippet(hit["content"], terms)

        return hits

    def _fuse_rrf(
        self,
        lexical_hits: List[Dict[str, Any]],
        semantic_hits: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Fuses lexical and dense vector rankings using Reciprocal Rank Fusion (RRF).
        Formula:
            RRF(d) = (w_lex / (k + rank_lex)) + (w_vec / (k + rank_vec))
        """
        fused: Dict[str, Dict[str, Any]] = {}

        # 1. Process Lexical Ranking
        for rank_idx, hit in enumerate(lexical_hits):
            cid = hit.get("chunk_id") or f"{hit.get('document_id')}_{hit.get('chunk_index', 0)}"
            rank = rank_idx + 1
            rrf_contrib = WEIGHT_LEXICAL / (RRF_K + rank)

            fused[cid] = {
                **hit,
                "lexical_rank": rank,
                "semantic_rank": None,
                "rrf_score": rrf_contrib,
                "score": rrf_contrib * 100.0  # scaled base score for reranker
            }

        # 2. Process Dense Vector Ranking
        for rank_idx, hit in enumerate(semantic_hits):
            cid = hit.get("chunk_id") or f"{hit.get('document_id')}_{hit.get('chunk_index', 0)}"
            rank = rank_idx + 1
            rrf_contrib = WEIGHT_SEMANTIC / (RRF_K + rank)

            if cid in fused:
                # Merge into existing hit
                existing = fused[cid]
                existing["semantic_rank"] = rank
                existing["semantic_score"] = hit.get("semantic_score")
                existing["rrf_score"] += rrf_contrib
                existing["score"] = existing["rrf_score"] * 100.0
            else:
                fused[cid] = {
                    **hit,
                    "lexical_rank": None,
                    "semantic_rank": rank,
                    "rrf_score": rrf_contrib,
                    "score": rrf_contrib * 100.0
                }

        # Sort candidate list by fused RRF score descending
        merged_hits = list(fused.values())
        merged_hits.sort(key=lambda x: x["rrf_score"], reverse=True)
        return merged_hits

    def _generate_highlighted_snippet(self, text: str, terms: List[str], max_len: int = 240) -> str:
        """Generates a snippet around the first matched term with HTML mark tags."""
        text_lower = text.lower()
        first_pos = len(text)
        found_term = None

        for term in terms:
            pos = text_lower.find(term)
            if 0 <= pos < first_pos:
                first_pos = pos
                found_term = term

        if found_term is None:
            snippet = text[:max_len] + ("..." if len(text) > max_len else "")
            return snippet

        # Center the snippet around the matched position
        start = max(0, first_pos - int(max_len / 3))
        end = min(len(text), start + max_len)
        snippet = text[start:end]

        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."

        # Apply highlight marks
        for term in set(terms):
            pattern = re.compile(rf"({re.escape(term)})", re.IGNORECASE)
            snippet = pattern.sub(r"<mark class='bg-amber-400/20 text-amber-200 px-1 rounded'>\1</mark>", snippet)

        return snippet


search_service = SearchService()
