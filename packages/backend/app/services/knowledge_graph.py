import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, or_

from app.models.document import Document, DocumentChunk
from app.models.graph import Entity, Relationship, EntityGrounding
from app.core.logging import logger

# Curated lexicons with pre-classified semantic types
KNOWN_TECHNOLOGIES = {
    "fastapi": "FastAPI",
    "opensearch": "OpenSearch",
    "qdrant": "Qdrant",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "sqlite": "SQLite",
    "redis": "Redis",
    "ollama": "Ollama",
    "pymupdf": "PyMuPDF",
    "networkx": "NetworkX",
    "fastembed": "FastEmbed",
    "react": "React",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "python": "Python",
    "docker": "Docker",
    "docker compose": "Docker Compose",
    "git": "Git",
    "github": "GitHub",
    "playwright": "Playwright",
    "tailwindcss": "TailwindCSS",
    "tailwind": "TailwindCSS",
    "onnx": "ONNX",
    "lucene": "Lucene",
    "elasticsearch": "Elasticsearch",
    "linux": "Linux",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "alembic": "Alembic",
    "sqlalchemy": "SQLAlchemy",
    "pydantic": "Pydantic",
    "beautifulsoup": "BeautifulSoup",
    "uvicorn": "Uvicorn",
}

KNOWN_CONCEPTS = {
    "reciprocal rank fusion": "Reciprocal Rank Fusion",
    "rrf": "Reciprocal Rank Fusion",
    "bm25": "BM25 Scoring",
    "vector search": "Vector Search",
    "semantic search": "Semantic Search",
    "hybrid search": "Hybrid Search",
    "approximate nearest neighbor": "Approximate Nearest Neighbor (ANN)",
    "ann": "Approximate Nearest Neighbor (ANN)",
    "lexical search": "Lexical Search",
    "knowledge graph": "Knowledge Graph",
    "inverted index": "Inverted Index",
    "cosine similarity": "Cosine Similarity",
    "precision anchor": "Precision Anchors",
    "document intelligence": "Document Intelligence",
    "privacy tier": "Privacy Tiers",
    "vault guard": "Vault Guard",
    "information retrieval": "Information Retrieval",
    "rag": "Retrieval-Augmented Generation (RAG)",
    "retrieval-augmented generation": "Retrieval-Augmented Generation (RAG)",
    "embeddings": "Vector Embeddings",
    "single source of truth": "Single Source of Truth (SSOT)",
    "ssot": "Single Source of Truth (SSOT)",
    "web crawler": "Web Crawler",
    "allowlist": "URL Allowlist",
    "robots.txt": "Robots.txt Parser",
    "chunking": "Semantic Chunking",
    "deduplication": "SHA-256 Deduplication",
    "grounded knowledge graph": "Grounded Knowledge Graph",
    "grounding": "Source Span Grounding",
}

KNOWN_ORGANIZATIONS = {
    "google": "Google",
    "google deepmind": "Google DeepMind",
    "openai": "OpenAI",
    "meta": "Meta",
    "meta ai": "Meta AI",
    "anthropic": "Anthropic",
    "apache": "Apache Software Foundation",
    "microsoft": "Microsoft",
    "elastic": "Elastic",
    "mozilla": "Mozilla",
    "aegis": "Aegis Engine",
}

# Regex relationship patterns
RELATION_PATTERNS = [
    (re.compile(r"\b(?P<src>[A-Z][A-Za-z0-9_\-\. ]{2,30})\s+(?:uses|utilizes|employs|adopts)\s+(?P<tgt>[A-Z][A-Za-z0-9_\-\. ]{2,30})\b", re.IGNORECASE), "USES"),
    (re.compile(r"\b(?P<src>[A-Z][A-Za-z0-9_\-\. ]{2,30})\s+(?:implements|executes|provides|supports)\s+(?P<tgt>[A-Z][A-Za-z0-9_\-\. ]{2,30})\b", re.IGNORECASE), "IMPLEMENTS"),
    (re.compile(r"\b(?P<src>[A-Z][A-Za-z0-9_\-\. ]{2,30})\s+(?:integrates with|connects to|interfaces with)\s+(?P<tgt>[A-Z][A-Za-z0-9_\-\. ]{2,30})\b", re.IGNORECASE), "INTEGRATES_WITH"),
    (re.compile(r"\b(?P<src>[A-Z][A-Za-z0-9_\-\. ]{2,30})\s+(?:depends on|requires|relies on)\s+(?P<tgt>[A-Z][A-Za-z0-9_\-\. ]{2,30})\b", re.IGNORECASE), "DEPENDS_ON"),
    (re.compile(r"\b(?P<src>[A-Z][A-Za-z0-9_\-\. ]{2,30})\s+(?:is powered by|is based on|builds upon)\s+(?P<tgt>[A-Z][A-Za-z0-9_\-\. ]{2,30})\b", re.IGNORECASE), "BASED_ON"),
    (re.compile(r"\b(?P<src>[A-Z][A-Za-z0-9_\-\. ]{2,30})\s+(?:created by|developed by|authored by)\s+(?P<tgt>[A-Z][A-Za-z0-9_\-\. ]{2,30})\b", re.IGNORECASE), "CREATED_BY"),
    (re.compile(r"\b(?P<src>[A-Z][A-Za-z0-9_\-\. ]{2,30})\s+(?:is a part of|component of|module of)\s+(?P<tgt>[A-Z][A-Za-z0-9_\-\. ]{2,30})\b", re.IGNORECASE), "PART_OF"),
]

# Capitalized proper noun phrase pattern
CAP_PHRASE_PATTERN = re.compile(r"\b([A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+){1,3})\b")
ACRONYM_PATTERN = re.compile(r"\b([A-Z]{2,6})\b")


class KnowledgeGraphService:
    """
    Phase 7: Grounded Knowledge Graph Service.
    Extracts entities and relationships from ingested document chunks, maintains
    source span grounding (character offsets, anchor labels, quote snippets),
    and powers graph search and topological visual exploration.
    """

    def extract_spans_from_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Scans chunk text for entities, calculating precise character span offsets
        [start, end], matched text, canonical name, and entity type.
        """
        extracted = []
        seen_spans: Set[Tuple[int, int]] = set()

        text_lower = text.lower()

        # 1. Known Technologies Lexicon
        for term, display_name in KNOWN_TECHNOLOGIES.items():
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            for m in pattern.finditer(text):
                start, end = m.span()
                if not any(s <= start and end <= e for s, e in seen_spans):
                    seen_spans.add((start, end))
                    extracted.append({
                        "name": display_name,
                        "canonical_name": display_name.lower(),
                        "entity_type": "TECHNOLOGY",
                        "span_start": start,
                        "span_end": end,
                        "matched_text": m.group(0),
                        "confidence": 0.95
                    })

        # 2. Known Concepts Lexicon
        for term, display_name in KNOWN_CONCEPTS.items():
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            for m in pattern.finditer(text):
                start, end = m.span()
                if not any(s <= start and end <= e for s, e in seen_spans):
                    seen_spans.add((start, end))
                    extracted.append({
                        "name": display_name,
                        "canonical_name": display_name.lower(),
                        "entity_type": "CONCEPT",
                        "span_start": start,
                        "span_end": end,
                        "matched_text": m.group(0),
                        "confidence": 0.90
                    })

        # 3. Known Organizations Lexicon
        for term, display_name in KNOWN_ORGANIZATIONS.items():
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            for m in pattern.finditer(text):
                start, end = m.span()
                if not any(s <= start and end <= e for s, e in seen_spans):
                    seen_spans.add((start, end))
                    extracted.append({
                        "name": display_name,
                        "canonical_name": display_name.lower(),
                        "entity_type": "ORGANIZATION",
                        "span_start": start,
                        "span_end": end,
                        "matched_text": m.group(0),
                        "confidence": 0.90
                    })

        # 4. Multi-word Capitalized Phrases
        stopwords = {"The", "This", "That", "These", "Those", "There", "When", "What", "Where", "How", "Why", "In", "On", "At", "For", "With", "By", "To", "From", "And", "Or", "If"}
        for m in CAP_PHRASE_PATTERN.finditer(text):
            start, end = m.span()
            matched = m.group(0).strip()
            first_word = matched.split()[0]
            if first_word in stopwords:
                continue
            if not any(s <= start and end <= e for s, e in seen_spans):
                seen_spans.add((start, end))
                extracted.append({
                    "name": matched,
                    "canonical_name": matched.lower(),
                    "entity_type": "CONCEPT",
                    "span_start": start,
                    "span_end": end,
                    "matched_text": matched,
                    "confidence": 0.75
                })

        # Sort by span start
        extracted.sort(key=lambda x: x["span_start"])
        return extracted

    def extract_relationships_from_text(
        self,
        text: str,
        entities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Discovers typed relationships between extracted entities based on syntactic
        dependency patterns and proximity co-occurrence within the chunk text.
        """
        relations = []
        entity_by_canonical = {e["canonical_name"]: e for e in entities}
        entity_names_lower = [e["canonical_name"] for e in entities]

        # 1. Syntactic pattern matches
        for pattern, rel_type in RELATION_PATTERNS:
            for m in pattern.finditer(text):
                src_raw = m.group("src").strip().lower()
                tgt_raw = m.group("tgt").strip().lower()

                # Find best matching entities
                src_entity = next((e for canon, e in entity_by_canonical.items() if canon in src_raw or src_raw in canon), None)
                tgt_entity = next((e for canon, e in entity_by_canonical.items() if canon in tgt_raw or tgt_raw in canon), None)

                if src_entity and tgt_entity and src_entity["canonical_name"] != tgt_entity["canonical_name"]:
                    span_start, span_end = m.span()
                    relations.append({
                        "source_name": src_entity["name"],
                        "source_canonical": src_entity["canonical_name"],
                        "target_name": tgt_entity["name"],
                        "target_canonical": tgt_entity["canonical_name"],
                        "relation_type": rel_type,
                        "weight": 1.5,
                        "span_start": span_start,
                        "span_end": span_end,
                        "context_snippet": self._get_context_snippet(text, span_start, span_end)
                    })

        # 2. Co-occurrence / Proximity associations (same sentence or within 140 chars)
        for i in range(len(entities)):
            for j in range(i + 1, min(i + 4, len(entities))):
                e1 = entities[i]
                e2 = entities[j]
                if e1["canonical_name"] == e2["canonical_name"]:
                    continue

                dist = abs(e2["span_start"] - e1["span_end"])
                if dist < 140:
                    # Check if already matched explicitly
                    already = any(
                        (r["source_canonical"] == e1["canonical_name"] and r["target_canonical"] == e2["canonical_name"]) or
                        (r["source_canonical"] == e2["canonical_name"] and r["target_canonical"] == e1["canonical_name"])
                        for r in relations
                    )
                    if not already:
                        span_start = min(e1["span_start"], e2["span_start"])
                        span_end = max(e1["span_end"], e2["span_end"])
                        relations.append({
                            "source_name": e1["name"],
                            "source_canonical": e1["canonical_name"],
                            "target_name": e2["name"],
                            "target_canonical": e2["canonical_name"],
                            "relation_type": "ASSOCIATED_WITH",
                            "weight": 1.0,
                            "span_start": span_start,
                            "span_end": span_end,
                            "context_snippet": self._get_context_snippet(text, span_start, span_end)
                        })

        return relations

    def _get_context_snippet(self, text: str, start: int, end: int, window: int = 80) -> str:
        s = max(0, start - window)
        e = min(len(text), end + window)
        prefix = "..." if s > 0 else ""
        suffix = "..." if e < len(text) else ""
        return f"{prefix}{text[s:e].strip()}{suffix}"

    async def extract_from_document(
        self,
        db: AsyncSession,
        document_id: str
    ) -> Dict[str, Any]:
        """
        Extracts entities, relationships, and grounded occurrences for a document
        and persists them into the PostgreSQL Knowledge Graph SSOT tables.
        """
        # Fetch document and chunks
        stmt = (
            select(Document)
            .where(Document.id == document_id)
        )
        res = await db.execute(stmt)
        doc = res.scalar_one_or_none()
        if not doc:
            return {"error": f"Document '{document_id}' not found", "extracted_entities": 0, "extracted_relations": 0}

        chunk_stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        chunk_res = await db.execute(chunk_stmt)
        chunks = chunk_res.scalars().all()

        # Delete existing groundings for this document to allow clean idempotent re-indexing
        del_grounding_stmt = delete(EntityGrounding).where(EntityGrounding.document_id == document_id)
        await db.execute(del_grounding_stmt)

        all_doc_entities: Dict[str, Entity] = {}
        total_groundings = 0
        total_relations_created = 0

        for chunk in chunks:
            text = chunk.content
            anchor = chunk.location_meta.get("anchor_label", f"Chunk #{chunk.chunk_index + 1}") if chunk.location_meta else f"Chunk #{chunk.chunk_index + 1}"
            
            # 1. Extract entity mentions
            spans = self.extract_spans_from_text(text)
            
            # Map canonical name to Entity DB object
            chunk_entities: List[Dict[str, Any]] = []
            for s in spans:
                canon = s["canonical_name"]
                
                # Check DB or local dict
                if canon in all_doc_entities:
                    entity_obj = all_doc_entities[canon]
                    entity_obj.mention_count += 1
                else:
                    existing_stmt = select(Entity).where(Entity.canonical_name == canon)
                    existing_res = await db.execute(existing_stmt)
                    entity_obj = existing_res.scalar_one_or_none()
                    
                    if entity_obj:
                        entity_obj.mention_count += 1
                        entity_obj.updated_at = datetime.now(timezone.utc)
                    else:
                        entity_obj = Entity(
                            name=s["name"],
                            canonical_name=canon,
                            entity_type=s["entity_type"],
                            mention_count=1,
                            properties={"discovered_in_doc": document_id}
                        )
                        db.add(entity_obj)
                        await db.flush()  # populate ID
                    all_doc_entities[canon] = entity_obj

                # Record entity grounding with physical source anchors
                context_snippet = self._get_context_snippet(text, s["span_start"], s["span_end"])
                grounding = EntityGrounding(
                    entity_id=entity_obj.id,
                    document_id=doc.id,
                    chunk_id=chunk.id,
                    chunk_index=chunk.chunk_index,
                    anchor_label=anchor,
                    span_start=s["span_start"],
                    span_end=s["span_end"],
                    matched_text=s["matched_text"],
                    context_snippet=context_snippet,
                    confidence=s["confidence"]
                )
                db.add(grounding)
                total_groundings += 1
                chunk_entities.append(s)

            # 2. Extract relationships between co-occurring entities
            if len(chunk_entities) >= 2:
                relations = self.extract_relationships_from_text(text, chunk_entities)
                for r in relations:
                    src_obj = all_doc_entities.get(r["source_canonical"])
                    tgt_obj = all_doc_entities.get(r["target_canonical"])
                    if not src_obj or not tgt_obj or src_obj.id == tgt_obj.id:
                        continue

                    # Check if relationship already exists
                    rel_stmt = (
                        select(Relationship)
                        .where(
                            Relationship.source_id == src_obj.id,
                            Relationship.target_id == tgt_obj.id,
                            Relationship.relation_type == r["relation_type"]
                        )
                    )
                    rel_res = await db.execute(rel_stmt)
                    rel_obj = rel_res.scalar_one_or_none()

                    if rel_obj:
                        rel_obj.weight += r["weight"]
                        rel_obj.updated_at = datetime.now(timezone.utc)
                    else:
                        rel_obj = Relationship(
                            source_id=src_obj.id,
                            target_id=tgt_obj.id,
                            relation_type=r["relation_type"],
                            weight=r["weight"],
                            description=f"{src_obj.name} {r['relation_type'].replace('_', ' ').lower()} {tgt_obj.name}",
                            properties={"discovered_in_doc": document_id}
                        )
                        db.add(rel_obj)
                        await db.flush()
                        total_relations_created += 1

                    # Record relationship grounding
                    rel_grounding = EntityGrounding(
                        relationship_id=rel_obj.id,
                        document_id=doc.id,
                        chunk_id=chunk.id,
                        chunk_index=chunk.chunk_index,
                        anchor_label=anchor,
                        span_start=r["span_start"],
                        span_end=r["span_end"],
                        matched_text=f"{src_obj.name} ➔ {tgt_obj.name}",
                        context_snippet=r["context_snippet"],
                        confidence=0.85
                    )
                    db.add(rel_grounding)

        await db.commit()
        logger.info(
            f"Knowledge Graph extraction complete for document '{doc.title}' ({document_id}): "
            f"{len(all_doc_entities)} entities, {total_relations_created} relations, {total_groundings} groundings."
        )

        return {
            "document_id": document_id,
            "document_title": doc.title,
            "entities_found": len(all_doc_entities),
            "relations_created": total_relations_created,
            "groundings_recorded": total_groundings
        }

    async def extract_from_all_documents(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Iterates across all ingested documents in PostgreSQL and constructs/refreshes
        the entire Grounded Knowledge Graph.
        """
        stmt = select(Document.id)
        res = await db.execute(stmt)
        doc_ids = [r[0] for r in res.all()]

        processed = 0
        total_entities = 0
        total_relations = 0

        for d_id in doc_ids:
            try:
                res_doc = await self.extract_from_document(db, d_id)
                total_entities += res_doc.get("entities_found", 0)
                total_relations += res_doc.get("relations_created", 0)
                processed += 1
            except Exception as e:
                logger.error(f"Error extracting graph for document {d_id}: {e}")

        stats = await self.get_stats(db)
        return {
            "documents_processed": processed,
            "stats": stats
        }

    async def get_graph(
        self,
        db: AsyncSession,
        query: Optional[str] = None,
        entity_types: Optional[List[str]] = None,
        min_weight: float = 0.5,
        limit_nodes: int = 100,
        limit_edges: int = 200
    ) -> Dict[str, Any]:
        """
        Retrieves the filtered graph topology (nodes, edges, node degrees, entity types)
        formatted for frontend interactive visual force layout.
        """
        # 1. Fetch Entities
        entity_stmt = select(Entity)
        if query:
            q_clean = f"%{query.strip().lower()}%"
            entity_stmt = entity_stmt.where(
                or_(
                    Entity.name.ilike(q_clean),
                    Entity.canonical_name.ilike(q_clean),
                    Entity.description.ilike(q_clean)
                )
            )
        if entity_types:
            entity_stmt = entity_stmt.where(Entity.entity_type.in_(entity_types))

        entity_stmt = entity_stmt.order_by(Entity.mention_count.desc()).limit(limit_nodes)
        entity_res = await db.execute(entity_stmt)
        entities = entity_res.scalars().all()
        entity_ids = {e.id for e in entities}

        if not entity_ids:
            return {"nodes": [], "edges": [], "stats": {"total_nodes": 0, "total_edges": 0}}

        # 2. Fetch Relationships connecting these entities
        rel_stmt = (
            select(Relationship)
            .where(
                Relationship.source_id.in_(entity_ids),
                Relationship.target_id.in_(entity_ids),
                Relationship.weight >= min_weight
            )
            .order_by(Relationship.weight.desc())
            .limit(limit_edges)
        )
        rel_res = await db.execute(rel_stmt)
        relationships = rel_res.scalars().all()

        # Compute degree per entity
        degrees: Dict[str, int] = {eid: 0 for eid in entity_ids}
        for r in relationships:
            degrees[r.source_id] = degrees.get(r.source_id, 0) + 1
            degrees[r.target_id] = degrees.get(r.target_id, 0) + 1

        nodes = []
        for e in entities:
            d = e.to_dict()
            d["degree"] = degrees.get(e.id, 0)
            nodes.append(d)

        edges = []
        for r in relationships:
            edges.append({
                "id": r.id,
                "source": r.source_id,
                "target": r.target_id,
                "relation_type": r.relation_type,
                "weight": r.weight,
                "description": r.description or f"{r.relation_type}",
            })

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
            }
        }

    async def get_entity_details(
        self,
        db: AsyncSession,
        entity_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves full entity details, its incoming/outgoing relations, and all
        grounded source citations with document titles, physical anchors, and quotes.
        """
        entity_stmt = select(Entity).where(Entity.id == entity_id)
        entity_res = await db.execute(entity_stmt)
        entity = entity_res.scalar_one_or_none()
        if not entity:
            return None

        # Connected relationships
        rel_stmt = (
            select(Relationship)
            .where(
                or_(
                    Relationship.source_id == entity_id,
                    Relationship.target_id == entity_id
                )
            )
            .order_by(Relationship.weight.desc())
        )
        rel_res = await db.execute(rel_stmt)
        rels = rel_res.scalars().all()

        connected_rels = []
        for r in rels:
            is_outgoing = (r.source_id == entity_id)
            other_id = r.target_id if is_outgoing else r.source_id
            other_stmt = select(Entity).where(Entity.id == other_id)
            other_res = await db.execute(other_stmt)
            other_node = other_res.scalar_one_or_none()

            connected_rels.append({
                "id": r.id,
                "relation_type": r.relation_type,
                "weight": r.weight,
                "direction": "outgoing" if is_outgoing else "incoming",
                "other_entity": other_node.to_dict() if other_node else {"id": other_id, "name": "Unknown"},
                "description": r.description
            })

        # Grounding citations with document metadata
        grounding_stmt = (
            select(EntityGrounding, Document.title, Document.mime_type, Document.source_type)
            .join(Document, Document.id == EntityGrounding.document_id)
            .where(EntityGrounding.entity_id == entity_id)
            .order_by(EntityGrounding.confidence.desc())
            .limit(30)
        )
        grounding_res = await db.execute(grounding_stmt)
        citations = []
        for g, doc_title, mime_type, src_type in grounding_res.all():
            citations.append({
                "grounding_id": g.id,
                "document_id": g.document_id,
                "document_title": doc_title,
                "source_type": src_type,
                "mime_type": mime_type,
                "chunk_id": g.chunk_id,
                "chunk_index": g.chunk_index,
                "anchor_label": g.anchor_label or f"Chunk #{g.chunk_index + 1}",
                "span_start": g.span_start,
                "span_end": g.span_end,
                "matched_text": g.matched_text,
                "context_snippet": g.context_snippet,
                "confidence": g.confidence,
                "created_at": g.created_at.isoformat() if g.created_at else None
            })

        result = entity.to_dict()
        result["relationships"] = connected_rels
        result["citations"] = citations
        result["degree"] = len(connected_rels)
        return result

    async def get_subgraph(
        self,
        db: AsyncSession,
        entity_id: str,
        depth: int = 1
    ) -> Dict[str, Any]:
        """
        Retrieves a 1-hop or 2-hop ego subgraph centered around an entity.
        """
        visited_nodes: Set[str] = {entity_id}
        frontier: Set[str] = {entity_id}

        for _ in range(min(depth, 2)):
            if not frontier:
                break
            rel_stmt = (
                select(Relationship)
                .where(
                    or_(
                        Relationship.source_id.in_(frontier),
                        Relationship.target_id.in_(frontier)
                    )
                )
            )
            rel_res = await db.execute(rel_stmt)
            next_frontier = set()
            for r in rel_res.scalars().all():
                if r.source_id not in visited_nodes:
                    next_frontier.add(r.source_id)
                    visited_nodes.add(r.source_id)
                if r.target_id not in visited_nodes:
                    next_frontier.add(r.target_id)
                    visited_nodes.add(r.target_id)
            frontier = next_frontier

        # Fetch all nodes in visited_nodes
        nodes_stmt = select(Entity).where(Entity.id.in_(visited_nodes))
        nodes_res = await db.execute(nodes_stmt)
        nodes = [e.to_dict() for e in nodes_res.scalars().all()]

        # Fetch all edges between these nodes
        edges_stmt = (
            select(Relationship)
            .where(
                Relationship.source_id.in_(visited_nodes),
                Relationship.target_id.in_(visited_nodes)
            )
        )
        edges_res = await db.execute(edges_stmt)
        edges = []
        for r in edges_res.scalars().all():
            edges.append({
                "id": r.id,
                "source": r.source_id,
                "target": r.target_id,
                "relation_type": r.relation_type,
                "weight": r.weight,
                "description": r.description
            })

        return {
            "center_node_id": entity_id,
            "depth": depth,
            "nodes": nodes,
            "edges": edges,
            "stats": {"node_count": len(nodes), "edge_count": len(edges)}
        }

    async def search_entities(
        self,
        db: AsyncSession,
        query: str,
        entity_type: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Searches entities by name or description.
        """
        q = f"%{query.strip().lower()}%"
        stmt = (
            select(Entity)
            .where(
                or_(
                    Entity.name.ilike(q),
                    Entity.canonical_name.ilike(q),
                    Entity.description.ilike(q)
                )
            )
        )
        if entity_type:
            stmt = stmt.where(Entity.entity_type == entity_type.upper())

        stmt = stmt.order_by(Entity.mention_count.desc()).limit(limit)
        res = await db.execute(stmt)
        return [e.to_dict() for e in res.scalars().all()]

    async def get_stats(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Aggregates graph topology metrics: total nodes, edges, groundings,
        and entity type distributions.
        """
        # Node count
        node_cnt_res = await db.execute(select(func.count(Entity.id)))
        total_nodes = node_cnt_res.scalar() or 0

        # Edge count
        edge_cnt_res = await db.execute(select(func.count(Relationship.id)))
        total_edges = edge_cnt_res.scalar() or 0

        # Grounding count
        ground_cnt_res = await db.execute(select(func.count(EntityGrounding.id)))
        total_groundings = ground_cnt_res.scalar() or 0

        # Type distribution
        type_stmt = (
            select(Entity.entity_type, func.count(Entity.id))
            .group_by(Entity.entity_type)
        )
        type_res = await db.execute(type_stmt)
        type_counts = {row[0]: row[1] for row in type_res.all()}

        # Top hub entities
        top_stmt = (
            select(Entity)
            .order_by(Entity.mention_count.desc())
            .limit(5)
        )
        top_res = await db.execute(top_stmt)
        top_entities = [e.to_dict() for e in top_res.scalars().all()]

        return {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "total_groundings": total_groundings,
            "entity_types": type_counts,
            "top_entities": top_entities
        }

    async def delete_entity(self, db: AsyncSession, entity_id: str) -> bool:
        """Deletes an entity and cascades to relationships and groundings."""
        stmt = select(Entity).where(Entity.id == entity_id)
        res = await db.execute(stmt)
        entity = res.scalar_one_or_none()
        if not entity:
            return False

        await db.delete(entity)
        await db.commit()
        logger.info(f"Deleted entity '{entity_id}'")
        return True


knowledge_graph_service = KnowledgeGraphService()
