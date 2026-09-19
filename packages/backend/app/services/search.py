import re
import time
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func

from app.models.document import Document, DocumentChunk
from app.services.opensearch import opensearch_service
from app.ranking.scorer import ranking_scorer
from app.core.logging import logger


class SearchService:
    async def search(
        self,
        query: str,
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

        # 1. Attempt OpenSearch BM25 search with candidate pool
        if opensearch_service.is_connected():
            candidate_limit = max(limit * 3, 50)
            os_result = opensearch_service.search(
                query_text=query,
                source_type=source_type,
                limit=candidate_limit,
                offset=0
            )
            if os_result is not None:
                raw_hits = os_result.get("results", [])
                reranked = ranking_scorer.rerank(query, raw_hits)
                paginated = reranked[offset:offset + limit]
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return {
                    "query": query,
                    "total": os_result.get("total", len(reranked)),
                    "latency_ms": duration_ms,
                    "engine": "opensearch_bm25_multi_signal",
                    "results": paginated
                }

        # 2. Resilient Database Fallback
        logger.info("Using Database Lexical Fallback Search")
        if not db:
            return {
                "query": query,
                "total": 0,
                "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
                "engine": "no_active_database",
                "results": []
            }

        # Query database chunks
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

        # Score matching chunks locally based on term occurrences and position
        scored_results = []
        for chunk, doc in rows:
            content_lower = chunk.content.lower()
            title_lower = doc.title.lower()

            # Calculate match score
            score = 0.0
            for term in terms:
                title_matches = title_lower.count(term)
                content_matches = content_lower.count(term)
                score += (title_matches * 3.0) + (content_matches * 1.0)

            # Highlight snippet
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

        # Apply multi-signal ranking reranker
        reranked_results = ranking_scorer.rerank(query, scored_results)
        paginated = reranked_results[offset:offset + limit]
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return {
            "query": query,
            "total": len(reranked_results),
            "latency_ms": duration_ms,
            "engine": "database_lexical_multi_signal",
            "results": paginated
        }

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
