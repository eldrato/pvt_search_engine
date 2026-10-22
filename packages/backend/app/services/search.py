import re
import time
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.models.document import Document, DocumentChunk
from app.services.opensearch import opensearch_service
from app.services.embedding import embedding_service
from app.services.qdrant import qdrant_service
from app.services.source_manager import source_manager
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
    - Privacy Tiers (Public/Private/Sensitive) and Per-Source toggles (Phase 6)
    """

    async def search(
        self,
        query: str,
        mode: str = "hybrid",
        source_type: Optional[str] = None,
        privacy_tier: Optional[str] = None,
        include_sensitive: bool = True,
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

        # Resolve allowed sources based on per-source toggles (Phase 6)
        if source_type:
            allowed_sources = [source_type]
        else:
            allowed_sources = await source_manager.get_enabled_source_types(db)

        # Resolve allowed privacy tiers (Phase 6)
        if privacy_tier:
            allowed_privacy_tiers = [privacy_tier.lower()]
        elif not include_sensitive:
            allowed_privacy_tiers = ["public", "private"]
        else:
            allowed_privacy_tiers = ["public", "private", "sensitive"]

        def _filter_privacy_and_source(items):
            filtered = []
            for item in items:
                item_tier = (item.get("privacy_tier") or "private").lower()
                if allowed_privacy_tiers and item_tier not in allowed_privacy_tiers:
                    continue
                item_src = item.get("source_type")
                if allowed_sources and item_src not in allowed_sources:
                    continue
                filtered.append(item)
            return filtered

        async def _verify_with_ssot(items):
            if not db or not items:
                return items
            doc_ids = list({c.get("document_id") for c in items if c.get("document_id")})
            if not doc_ids:
                return items
            stmt = select(Document.id, Document.privacy_tier, Document.source_type).where(Document.id.in_(doc_ids))
            res = await db.execute(stmt)
            valid_docs = {row[0]: (row[1], row[2]) for row in res.all()}
            verified = []
            for c in items:
                did = c.get("document_id")
                if did in valid_docs:
                    c["privacy_tier"] = valid_docs[did][0] or "private"
                    c["source_type"] = valid_docs[did][1]
                    verified.append(c)
            return verified

        if mode == "lexical":
            candidates, engine_name = await self._search_lexical(
                query=query,
                source_type=source_type,
                allowed_sources=allowed_sources,
                allowed_privacy_tiers=allowed_privacy_tiers,
                limit=candidate_limit,
                db=db
            )
            candidates = await _verify_with_ssot(candidates)
            candidates = _filter_privacy_and_source(candidates)
            # Mark lexical ranks
            for idx, c in enumerate(candidates):
                c["lexical_rank"] = idx + 1
            reranked = ranking_scorer.rerank(query, candidates)
            engine = f"{engine_name}_multi_signal"

        elif mode == "semantic":
            candidates = await self._search_semantic(
                query=query,
                source_type=source_type,
                allowed_sources=allowed_sources,
                allowed_privacy_tiers=allowed_privacy_tiers,
                limit=candidate_limit
            )
            candidates = await _verify_with_ssot(candidates)
            candidates = _filter_privacy_and_source(candidates)
            # Mark semantic ranks
            for idx, c in enumerate(candidates):
                c["semantic_rank"] = idx + 1
            reranked = ranking_scorer.rerank(query, candidates)
            engine = "qdrant_vector_multi_signal"

        else:  # "hybrid" (default)
            lexical_hits, _ = await self._search_lexical(
                query=query,
                source_type=source_type,
                allowed_sources=allowed_sources,
                allowed_privacy_tiers=allowed_privacy_tiers,
                limit=candidate_limit,
                db=db
            )
            semantic_hits = await self._search_semantic(
                query=query,
                source_type=source_type,
                allowed_sources=allowed_sources,
                allowed_privacy_tiers=allowed_privacy_tiers,
                limit=candidate_limit
            )

            lexical_hits = await _verify_with_ssot(lexical_hits)
            semantic_hits = await _verify_with_ssot(semantic_hits)

            # Apply Reciprocal Rank Fusion
            fused_candidates = self._fuse_rrf(lexical_hits, semantic_hits)
            fused_candidates = _filter_privacy_and_source(fused_candidates)
            reranked = ranking_scorer.rerank(query, fused_candidates)
            engine = "hybrid_rrf_multi_signal"

        matched_entities = []
        if db:
            try:
                from app.services.knowledge_graph import knowledge_graph_service
                matched_entities = await knowledge_graph_service.search_entities(db, query, limit=5)
            except Exception:
                matched_entities = []

        return {
            "query": query,
            "total": len(reranked),
            "latency_ms": duration_ms,
            "engine": engine,
            "results": paginated,
            "knowledge_entities": matched_entities
        }

    async def _search_lexical(
        self,
        query: str,
        source_type: Optional[str] = None,
        allowed_sources: Optional[List[str]] = None,
        allowed_privacy_tiers: Optional[List[str]] = None,
        limit: int = 50,
        db: Optional[AsyncSession] = None
    ) -> tuple[List[Dict[str, Any]], str]:
        """Performs lexical search via OpenSearch BM25 or DB SQL fallback with privacy and source filters."""
        if opensearch_service.is_connected():
            os_result = opensearch_service.search(
                query_text=query,
                source_type=source_type,
                allowed_sources=allowed_sources,
                allowed_privacy_tiers=allowed_privacy_tiers,
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
        elif allowed_sources:
            stmt = stmt.where(Document.source_type.in_(allowed_sources))

        if allowed_privacy_tiers:
            stmt = stmt.where(Document.privacy_tier.in_(allowed_privacy_tiers))

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
                "chunk_id": f"{doc.id}_{chunk.chunk_index}",
                "raw_chunk_id": chunk.id,
                "document_id": doc.id,
                "title": doc.title,
                "snippet": snippet,
                "content": chunk.content,
                "score": round(max(0.5, score), 3),
                "source_type": doc.source_type,
                "privacy_tier": getattr(doc, "privacy_tier", "private") or "private",
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
        allowed_sources: Optional[List[str]] = None,
        allowed_privacy_tiers: Optional[List[str]] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Performs dense vector retrieval via local FastEmbed + Qdrant with privacy and source filters."""
        if not qdrant_service.is_connected():
            return []

        query_vec = embedding_service.embed_query(query)
        hits = qdrant_service.search_vectors(
            query_vector=query_vec,
            source_type=source_type,
            allowed_sources=allowed_sources,
            allowed_privacy_tiers=allowed_privacy_tiers,
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

        def _hit_key(h: Dict[str, Any]) -> str:
            doc_id = h.get("document_id")
            chunk_idx = h.get("chunk_index", 0)
            if doc_id:
                return f"{doc_id}_{chunk_idx}"
            return str(h.get("chunk_id", ""))

        # 1. Process Lexical Ranking
        for rank_idx, hit in enumerate(lexical_hits):
            cid = _hit_key(hit)
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
            cid = _hit_key(hit)
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
