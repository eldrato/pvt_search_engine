import re
import math
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field


class ScoreBreakdown(BaseModel):
    base_bm25: float = Field(..., description="Raw BM25 / lexical / fused base match score")
    title_boost: float = Field(..., description="Multiplier for title and section anchor matches [1.0 - 1.6]")
    authority_boost: float = Field(..., description="Multiplier for document provenance/source type [1.0 - 1.5]")
    freshness_boost: float = Field(..., description="Multiplier based on document age half-life decay [0.5 - 1.0]")
    phrase_boost: float = Field(..., description="Multiplier for exact phrase proximity [1.0 - 1.25]")
    final_score: float = Field(..., description="Final composite relevance score")
    semantic_similarity: Optional[float] = Field(None, description="Dense vector cosine similarity score [0.0 - 1.0]")
    lexical_rank: Optional[int] = Field(None, description="Rank in lexical BM25 retrieval stream")
    semantic_rank: Optional[int] = Field(None, description="Rank in dense vector retrieval stream")
    rrf_score: Optional[float] = Field(None, description="Reciprocal Rank Fusion score before multi-signal boosts")
    explanation: List[str] = Field(default_factory=list, description="Human-readable explanation of ranking signals")


class RankingScorer:
    """
    Multi-signal ranking engine combining:
    - Base Lexical BM25 score
    - Title & anchor proximity prominence
    - Document authority and provenance
    - Half-life freshness decay
    - Exact contiguous phrase match
    """

    DEFAULT_SOURCE_WEIGHTS = {
        "note": 1.30,     # Personal thoughts and research notes have highest authority
        "upload": 1.20,   # User-uploaded books/PDFs/documents
        "code": 1.15,     # Local source code
        "web": 1.00       # Allowlisted web crawl content
    }

    # Half-life parameters (90 days half-life with a 0.50 evergreen floor)
    HALF_LIFE_DAYS = 90.0
    EVERGREEN_FLOOR = 0.50

    def compute_title_boost(
        self,
        query: str,
        title: Optional[str],
        anchor_label: Optional[str]
    ) -> Tuple[float, Optional[str]]:
        title = (title or "").strip().lower()
        anchor = (anchor_label or "").strip().lower()
        clean_query = query.strip().lower()
        terms = [t for t in re.findall(r"\w+", clean_query) if len(t) > 1]
        if not terms:
            terms = [clean_query]

        boost = 1.0
        reasons = []

        # 1. Exact query match in title
        if clean_query and clean_query in title:
            boost += 0.50
            reasons.append("Exact query matches document title (+50%)")
        else:
            # Check term coverage in title
            matched_terms = sum(1 for t in set(terms) if t in title)
            if matched_terms == len(set(terms)):
                boost += 0.30
                reasons.append(f"All query terms appear in title (+30%)")
            elif matched_terms > 0:
                fraction = matched_terms / len(set(terms))
                added = round(0.20 * fraction, 2)
                boost += added
                reasons.append(f"Title matches {matched_terms}/{len(set(terms))} query terms (+{int(added*100)}%)")

        # 2. Anchor match (e.g. section title / header)
        if anchor and any(t in anchor for t in terms):
            boost += 0.10
            reasons.append(f"Anchor label matches query terms ('{anchor_label}') (+10%)")

        # Cap at 1.60
        boost = min(boost, 1.60)
        boost = round(boost, 3)

        explanation = "; ".join(reasons) if reasons else "No special title match (1.00x)"
        return boost, explanation

    def compute_authority_boost(
        self,
        source_type: Optional[str],
        location_meta: Optional[Dict[str, Any]] = None
    ) -> Tuple[float, str]:
        source = (source_type or "").lower().strip()
        weight = self.DEFAULT_SOURCE_WEIGHTS.get(source, 1.0)
        explanation = f"Source authority: {source or 'unknown'} ({weight:.2f}x)"

        # Web domain confidence boost (e.g. docs, wikis, github)
        if source == "web" and location_meta:
            domain = str(location_meta.get("domain", "")).lower()
            if any(k in domain for k in ["docs.", "wiki.", "developer.", "github.io"]):
                weight += 0.10
                weight = round(weight, 2)
                explanation = f"Curated documentation domain '{domain}' ({weight:.2f}x)"

        return weight, explanation

    def compute_freshness_boost(
        self,
        created_at: Optional[Any]
    ) -> Tuple[float, str]:
        if not created_at:
            return 0.90, "No creation timestamp available (default 0.90x)"

        dt: Optional[datetime] = None
        if isinstance(created_at, datetime):
            dt = created_at
        elif isinstance(created_at, str):
            try:
                # Handle ISO strings with Z or timezone
                clean_str = created_at.replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean_str)
            except Exception:
                return 0.90, "Timestamp parse fallback (default 0.90x)"

        if dt is None:
            return 0.90, "Invalid timestamp (default 0.90x)"

        # Ensure timezone aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)

        delta_seconds = max(0.0, (now - dt).total_seconds())
        delta_days = delta_seconds / 86400.0

        decay_constant = math.log(2) / self.HALF_LIFE_DAYS
        decay_factor = math.exp(-decay_constant * delta_days)
        freshness = self.EVERGREEN_FLOOR + (1.0 - self.EVERGREEN_FLOOR) * decay_factor
        freshness = round(max(self.EVERGREEN_FLOOR, min(1.0, freshness)), 3)

        if delta_days < 1.0:
            age_desc = "indexed today"
        elif delta_days < 30.0:
            age_desc = f"{int(delta_days)} days old"
        elif delta_days < 365.0:
            age_desc = f"{int(delta_days / 30.0)} months old"
        else:
            age_desc = f"{delta_days / 365.0:.1f} years old"

        explanation = f"Freshness factor {freshness:.2f}x ({age_desc})"
        return freshness, explanation

    def compute_phrase_boost(
        self,
        query: str,
        content: Optional[str]
    ) -> Tuple[float, str]:
        content = (content or "").lower()
        clean_query = query.strip().lower()
        terms = [t for t in re.findall(r"\w+", clean_query) if len(t) > 1]

        # Single word query has no phrase proximity
        if len(terms) < 2:
            return 1.0, "Single term query (1.00x)"

        # 1. Exact contiguous phrase
        exact_pattern = r"\b" + r"\s+".join(re.escape(t) for t in terms) + r"\b"
        if re.search(exact_pattern, content):
            return 1.25, "Exact contiguous phrase match (+25%)"

        # 2. Word proximity: terms appear within a sliding window of 15 words
        words = re.findall(r"\w+", content)
        if len(words) >= len(terms):
            unique_terms = set(terms)
            for i in range(len(words) - len(terms) + 1):
                window = set(words[i:i + 15])
                if unique_terms.issubset(window):
                    return 1.10, "High term proximity (<15 words apart, +10%)"

        return 1.0, "Terms spread across chunk (1.00x)"

    def score_hit(
        self,
        query: str,
        hit: Dict[str, Any]
    ) -> Tuple[float, ScoreBreakdown]:
        raw_score = float(hit.get("score") or 1.0)
        # Ensure raw base score is non-zero
        base_bm25 = max(0.1, round(raw_score, 4))

        title_boost, title_reason = self.compute_title_boost(
            query=query,
            title=hit.get("title"),
            anchor_label=hit.get("anchor_label")
        )

        auth_boost, auth_reason = self.compute_authority_boost(
            source_type=hit.get("source_type"),
            location_meta=hit.get("location_meta")
        )

        fresh_boost, fresh_reason = self.compute_freshness_boost(
            created_at=hit.get("created_at")
        )

        phrase_boost, phrase_reason = self.compute_phrase_boost(
            query=query,
            content=hit.get("content")
        )

        final_score = base_bm25 * title_boost * auth_boost * fresh_boost * phrase_boost
        final_score = round(final_score, 4)

        semantic_similarity = hit.get("semantic_score")
        if semantic_similarity is not None:
            semantic_similarity = round(float(semantic_similarity), 4)

        lexical_rank = hit.get("lexical_rank")
        semantic_rank = hit.get("semantic_rank")
        rrf_score = hit.get("rrf_score")
        if rrf_score is not None:
            rrf_score = round(float(rrf_score), 5)

        base_label = "Base fused RRF score" if rrf_score is not None else "Base match score"
        explanations = [
            f"{base_label}: {base_bm25:.3f}",
            title_reason,
            auth_reason,
            fresh_reason,
            phrase_reason
        ]

        if semantic_similarity is not None:
            explanations.append(f"Semantic similarity: {semantic_similarity:.3f} (cosine distance)")
        if lexical_rank is not None and semantic_rank is not None:
            explanations.append(f"Hybrid RRF positions: BM25 #{lexical_rank} · Vector #{semantic_rank}")
        elif lexical_rank is not None:
            explanations.append(f"Lexical BM25 position: #{lexical_rank}")
        elif semantic_rank is not None:
            explanations.append(f"Dense vector position: #{semantic_rank}")

        breakdown = ScoreBreakdown(
            base_bm25=base_bm25,
            title_boost=title_boost,
            authority_boost=auth_boost,
            freshness_boost=fresh_boost,
            phrase_boost=phrase_boost,
            final_score=final_score,
            semantic_similarity=semantic_similarity,
            lexical_rank=lexical_rank,
            semantic_rank=semantic_rank,
            rrf_score=rrf_score,
            explanation=explanations
        )

        return final_score, breakdown

    def rerank(
        self,
        query: str,
        hits: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Reranks a list of candidate hits using multi-signal scoring.
        Updates each hit's 'score' with the composite score and attaches 'score_breakdown'.
        Returns hits sorted in descending order of final_score.
        """
        if not hits:
            return []

        scored_hits = []
        for hit in hits:
            final_score, breakdown = self.score_hit(query, hit)
            hit_copy = dict(hit)
            hit_copy["score"] = final_score
            hit_copy["score_breakdown"] = breakdown.model_dump()
            scored_hits.append(hit_copy)

        scored_hits.sort(key=lambda x: x["score"], reverse=True)
        return scored_hits


ranking_scorer = RankingScorer()
