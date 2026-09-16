# Aegis — Comprehensive System Architecture Specification

## 1. System Overview & Core Philosophy

**Aegis** is a self-hosted, privacy-first personal search and research engine designed for single-user deployment. It bridges the gap between personal knowledge management, local document indexing, controlled web search, and evidence-backed AI research.

### Core Architectural Invariants
1. **Privacy-First Posture**: All raw documents, vector embeddings, lexical inverted indices, knowledge graphs, and LLM reasoning remain 100% local. Zero external telemetry or analytics.
2. **Single Source of Truth (SSOT)**: PostgreSQL is the authoritative system of record. External indices (OpenSearch for lexical search, Qdrant for vector embeddings) are derived state that can be wiped and fully rebuilt at any time from Postgres + raw document storage.
3. **Retrieval-Grounded AI**: The AI / RAG layer operates strictly on retrieved source spans. LLM inference cannot present facts without verified citations linked to explicit document line numbers, page numbers, or snapshot section anchors.
4. **Modular Monolith**: Clean python package structure separating ingestion, retrieval, crawler, graph, and RAG modules, running inside a unified FastAPI process until measured metrics require independent scaling.

---

## 2. Full Architecture Diagram

```
                                  ┌──────────────────────────────────────────────┐
                                  │   Frontend (Next.js 14 / TypeScript / CSS)   │
                                  │   - Modern Search UI & Query Syntaxes       │
                                  │   - Evidence Drawer & Citation Inspector     │
                                  │   - Interactive Graph Exploration Canvas     │
                                  └──────────────────────┬───────────────────────┘
                                                         │ HTTPS (TLS)
                                  ┌──────────────────────▼───────────────────────┐
                                  │   Reverse Proxy (Caddy / Nginx)              │
                                  │   - TLS termination & Static File Server     │
                                  │   - Rate limiting & Local IP Binding         │
                                  └──────────────────────┬───────────────────────┘
                                                         │ REST / WebSockets
┌────────────────────────────────────────────────────────▼────────────────────────────────────────────────────────┐
│ FastAPI Application Core (Python 3.11 Modular Monolith)                                                         │
│                                                                                                                 │
│ ┌───────────────────────────┐  ┌───────────────────────────┐  ┌──────────────────────────────────────────────┐ │
│ │   Query Understanding     │  │     Web Crawler Engine    │  │        Document Ingestion Pipeline           │ │
│ │   - Operator Parser       │  │   - Scrapy + Playwright   │  │   - PyMuPDF / python-docx / HTML Parsers     │ │
│ │   - Intent Classifier     │  │   - Frontier & Robots.txt │  │   - Tesseract OCR Engine                     │ │
│ │   - Sub-query Expansion   │  │   - Domain Allowlisting   │  │   - Structure-Preserving Chunking            │ │
│ └─────────────┬─────────────┘  └─────────────┬─────────────┘  └──────────────────────┬───────────────────────┘ │
│               │                              │                                       │                          │
│ ┌─────────────▼─────────────┐                │                ┌──────────────────────▼───────────────────────┐ │
│ │ Multi-Modal Retrieval Engine│               │                │       Local Embedding Pipeline               │ │
│ │ - OpenSearch BM25 Lexical │                │                │     - ONNX / HuggingFace Local Models        │ │
│ │ - Qdrant Dense Vector     │                │                │     - Asynchronous Batch Processing          │ │
│ │ - Knowledge Graph Traversal│               │                └──────────────────────┬───────────────────────┘ │
│ └─────────────┬─────────────┘                │                                       │                          │
│               │                              │                                       │                          │
│ ┌─────────────▼─────────────┐                │                                       │                          │
│ │   Ranking & Fusion Engine │                │                                       │                          │
│ │ - Reciprocal Rank Fusion  │                │                                       │                          │
│ │ - Freshness & Quality     │                │                                       │                          │
│ │ - Score Explanation ("Why")│               │                                       │                          │
│ └─────────────┬─────────────┘                │                                       │                          │
│               │                              │                                       │                          │
│ ┌─────────────▼─────────────┐                │                                       │                          │
│ │    AI / RAG Layer         │                │                                       │                          │
│ │ - Citation Validator      │                │                                       │                          │
│ │ - Ollama Local LLM Client │                │                                       │                          │
│ │ - Research Agent Loop     │                │                                       │                          │
│ └───────────────────────────┘                │                                       │                          │
└──────────────────┬───────────────────────────┴───────────────────────────────────────┴──────────────────────────┘
                   │
  ┌────────────────┼──────────────────────────────┬──────────────────────────────┐
  │                │                              │                              │
┌─▼──────────────┐ ┌▼───────────────────────────┐ ┌▼───────────────────────────┐ ┌▼───────────────────────────┐
│   PostgreSQL   │ │        OpenSearch         │ │          Qdrant           │ │           Redis           │
│ System of      │ │  BM25 Inverted Text Index │ │   Dense Vector DB          │ │ Queue, Rate-Limiting &    │
│ Record (SSOT)  │ │  Stemming & Stopwords     │ │   HNSW Vector Indexing    │ │ Cache Management          │
└────────────────┘ └───────────────────────────┘ └───────────────────────────┘ └───────────────────────────┘
```

---

## 3. Core Component Responsibilities

| Component | Responsible Modules | Primary Function & Responsibilities |
| :--- | :--- | :--- |
| **API & Gateway** | FastAPI, Pydantic | Query parsing, validation, endpoint routing, streaming responses, security middleware. |
| **Ingestion Pipeline** | PyMuPDF, python-docx, Tesseract | Extracts raw text, preserves structural anchors (page, section, line), generates chunk hashes. |
| **Embedding Engine** | ONNX Runtime / HuggingFace Transformers | Generates dense embeddings locally without external API calls. |
| **Lexical Engine** | OpenSearch | Provides BM25 keyword matching, exact phrase queries, boolean operators, fuzzy matching. |
| **Vector Engine** | Qdrant | Performs approximate nearest neighbor (ANN) search over chunk embeddings. |
| **Fusion & Rerank** | Custom Python Engine | Fuses lexical and vector scores via Reciprocal Rank Fusion (RRF) and applies custom scoring signals. |
| **Web Crawler** | Scrapy + Playwright | Fetches allowlisted web content, respects `robots.txt`, renders JS, handles rate-limits and retries. |
| **Knowledge Graph** | NetworkX / Postgres Graph Table | Stores extracted entities (people, concepts, technologies) and typed relationships with source provenance. |
| **RAG & Agent Engine**| Ollama API Client, Custom Validation | Manages LLM prompting, citation verification against retrieved spans, multi-step sub-query execution. |

---

## 4. Ingestion & Search Data Flows

### Ingestion Pipeline Flow
```
[Uploaded Document / Crawled Web Page]
             │
             ▼
[Format Parser: PyMuPDF / docx / HTML / OCR]
             │
             ▼
[Structure Extractor: Metadata + Page/Line Locators]
             │
             ▼
[Chunker: Overlapping Sliding Window (512 tokens)]
             │
             ▼
[PostgreSQL: Save Raw Document, Metadata & Chunks (SSOT)]
             ├───────────────────────────────────────────┐
             ▼                                           ▼
[Local Embedding Model]                         [OpenSearch Ingestion]
             │                                           │
             ▼                                           ▼
[Qdrant: Insert Vectors + Payload]              [OpenSearch: BM25 Inverted Index]
```

### Search Execution Flow
```
[User Query] ──> [Query Understanding Parser (Operators, Site, Filetype)]
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
   [OpenSearch BM25 Query]           [Qdrant Vector ANN Query]
            │                                 │
            └────────────────┬────────────────┘
                             ▼
              [Reciprocal Rank Fusion (RRF)]
                             │
                             ▼
         [Scoring Engine (Authority, Freshness, Personal)]
                             │
                             ▼
              [Filtered Context & Score Explanation]
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
   [Standard Search Results]       [Private RAG LLM Generation]
                                            │
                                            ▼
                                [Citation Validation Engine]
```

---

## 5. Security, Privacy & Data Isolation

1. **Local-Only Binding**: All database containers (Postgres, OpenSearch, Qdrant, Redis) and the Ollama server bind strictly to `127.0.0.1`.
2. **Untrusted Input Boundary**: All external web content crawled or uploaded is sanitized and treated as **data only**. HTML tags, scripts, and prompt injection payloads (e.g. "ignore previous instructions") are stripped and isolated.
3. **Citation & Verification Boundary**: Any LLM-generated answer undergoes an automated post-generation pass that cross-references `[Citation X]` markers against the exact string offsets in retrieved chunks. Unverified claims are explicitly flagged or excised.

---

## 6. Development Phasing Overview

- **Phase 0: Design & Setup** — Architecture specification, repository structure, environment configuration.
- **Phase 1: Lexical Search Core** — PyMuPDF/docx/text ingestion, Postgres SSOT storage, OpenSearch BM25 index, basic REST search API.
- **Phase 2: Controlled Web Crawler** — Allowlist enforcement, URL frontier in Redis, Playwright rendering, crawl queue management.
- **Phase 3: Ranking & Quality** — Multi-factor scoring model, score component breakdown, "Why this result?" UI inspector.
- **Phase 4: Semantic Search & Evaluation** — Local embedding integration, Qdrant ANN search, RRF fusion, benchmark metric suit (Precision, Recall, MRR, NDCG).
- **Phase 5: Document Intelligence** — Granular location tracking (page, paragraph, source file line numbers), PDF highlights.
- **Phase 6: Personal Knowledge Engine** — Privacy tiers (Public/Private/Sensitive), per-source indexing management.
- **Phase 7: Knowledge Graph** — Grounded entity & relationship extraction, interactive visual exploration UI.
- **Phase 8: Private RAG** — Local LLM integration via Ollama, strict context injection, citation validation.
- **Phase 9: Autonomous Research Agent** — Multi-step query decomposition, iterative retrieval, synthesis & trace visualizer.
- **Phase 10: Production Hardening** — Observability (Prometheus/Grafana), Docker Compose orchestration, security audit.
