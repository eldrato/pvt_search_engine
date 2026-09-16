# Aegis — Private Personal Search & Research Engine

[![Privacy First](https://img.shields.io/badge/Privacy-100%25%20Local-emerald.svg)](#privacy-first-architecture)
[![Architecture](https://img.shields.io/badge/Architecture-Modular%20Monolith-blue.svg)](./system-architecture.md)
[![License](https://img.shields.io/badge/License-MIT-purple.svg)](#license)

**Aegis** is a self-hosted, privacy-first personal search and research engine. It empowers a single user to search across an allowlisted slice of the web, personal documents (PDF, DOCX, Markdown, Source Code), notes, bookmarks, and a personal knowledge graph using hybrid keyword + semantic search and evidence-backed local AI.

---

## 🌟 Key Features & Core Principles

- 🔒 **100% Privacy-First Architecture**: Local storage, local vector embeddings, local LLM inference (via Ollama), and local search history. No data leaves your machine unless explicitly opted into.
- 🔍 **Hybrid Multi-Modal Retrieval**: Combines OpenSearch BM25 keyword matching with Qdrant dense vector semantic search using Reciprocal Rank Fusion (RRF).
- 📑 **Document Intelligence & Precision Anchors**: Ingests PDFs, Word documents, Markdown, HTML, and code files while preserving exact page numbers, line numbers (`file.py:84`), and section headers.
- 🤖 **Evidence-Backed Private RAG**: Answers queries using local LLMs grounded strictly in retrieved context. Every assertion requires verifiable source spans.
- 🕸️ **Grounded Knowledge Graph**: Automatically extracts entities and relationships from ingested documents with traceable source citations.
- 🕵️ **Autonomous Research Agent**: Decomposes complex research queries, generates iterative search sub-queries, dedups evidence, and synthesizes cited research briefs.

---

## 🏗️ System Architecture

Aegis is built as a **modular monolith** running behind a reverse proxy.

```
Frontend (Next.js / React / TypeScript / Tailwind CSS)
   └─► Reverse Proxy (Caddy / Nginx, TLS termination)
        └─► FastAPI Application Core (Python 3.11 Modular Monolith)
             ├─ Query Understanding Engine (Operators & Syntax)
             ├─ Ingestion Pipeline (PyMuPDF, docx, Tesseract OCR)
             ├─ Controlled Web Crawler (Scrapy + Playwright)
             ├─ Local Embedding Engine (HuggingFace / ONNX)
             ├─ Parallel Hybrid Retrieval (BM25 + Dense Vector + Graph)
             ├─ Fusion & Ranking Engine (RRF, Authority, Freshness)
             ├─ Knowledge Graph Module
             └─ Private RAG & Research Agent (Ollama Local LLM)
   Storage Tier:
      ├─ PostgreSQL (System of Record / Single Source of Truth)
      ├─ OpenSearch (Lexical Inverted BM25 Index)
      ├─ Qdrant (Dense Vector Database)
      └─ Redis (Job Queues, Rate Limiting & Query Cache)
```

> 📖 **Full Architectural Specification**: See [system-architecture.md](./system-architecture.md) for detailed data flow diagrams, security boundaries, and component interaction tables.

---

## 🛠️ Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | Next.js 14, React 18, TypeScript, Tailwind CSS, Lucide Icons |
| **Backend API** | Python 3.11, FastAPI, Pydantic v2, SQLAlchemy, AsyncIO |
| **Databases** | PostgreSQL 16 (SSOT), OpenSearch 2.x (BM25), Qdrant (Vectors), Redis 7 (Cache/Queue) |
| **Ingestion & OCR** | PyMuPDF (fitz), python-docx, BeautifulSoup4, Tesseract OCR |
| **Embeddings & LLM**| HuggingFace Transformers / ONNX Runtime, Ollama (Local Llama3 / Qwen) |
| **Web Crawler** | Scrapy, Playwright for JavaScript rendering |
| **DevOps & Proxy** | Docker, Docker Compose, Caddy / Nginx, pytest |

---

## 🗺️ Development Roadmap & Phases

- [x] **Phase 0: Architecture & Specs** — Define PRD, system architecture, data models, and repository layout.
- [ ] **Phase 1: Basic Lexical Search Core** — Document upload/ingestion, Postgres SSOT storage, OpenSearch BM25 keyword search & results UI.
- [ ] **Phase 2: Controlled Web Crawler** — Allowlist-based crawling, URL frontier management, JS rendering via Playwright, `robots.txt` compliance.
- [ ] **Phase 3: Search Quality & Ranking** — Multi-signal ranking function (BM25 + authority + freshness), "Why this result?" breakdown inspector.
- [ ] **Phase 4: Semantic Search & Evaluation** — Local vector embeddings, Qdrant integration, RRF fusion, automated benchmark metric suite (Precision, Recall, MRR, NDCG).
- [ ] **Phase 5: Document Intelligence** — Exact location tracking (pages, paragraphs, code lines), inline PDF highlighter.
- [ ] **Phase 6: Personal Knowledge Engine** — Data classification (Public/Private/Sensitive), source enable/disable toggle.
- [ ] **Phase 7: Grounded Knowledge Graph** — Entity & relationship extraction with source span grounding, interactive graph visualizer.
- [ ] **Phase 8: Private RAG & Citation Inspector** — Local Ollama LLM integration, strict prompt sandbox, automated citation validator.
- [ ] **Phase 9: Autonomous Research Agent** — Multi-step query planner, iterative web/doc retrieval, research brief synthesizer.
- [ ] **Phase 10: Production Hardening** — Prometheus/Grafana observability, security sandbox audit, CLI & browser extension.

---

## 💻 Quick Start & Local Setup

### Prerequisites
- **Python**: `3.11+`
- **Node.js**: `18.x` or `20.x`
- **Docker & Docker Compose**: Installed and running
- **Ollama**: Installed locally with models pulled (e.g. `ollama pull llama3:8b`)

### 1. Clone & Set Up Directory
```bash
git clone https://github.com/your-org/aegis.git
cd aegis
```

### 2. Environment Configuration
Create a `.env` file from the default template:
```bash
cp .env.example .env
```

### 3. Start Storage Infrastructure
Launch PostgreSQL, OpenSearch, Qdrant, and Redis using Docker Compose:
```bash
docker-compose up -d postgres opensearch qdrant redis
```

### 4. Backend Setup & Run
```bash
# Create Python virtual environment
python -m venv venv
# Activate virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r backend/requirements.txt

# Run database migrations
alembic upgrade head

# Start FastAPI dev server
uvicorn backend.main:app --reload --port 8000
```

### 5. Frontend Setup & Run
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 🔒 Security Boundary & Storage Invariants

1. **PostgreSQL is the Single Source of Truth**: All original files, web page snapshots, metadata, and user configs reside in Postgres.
2. **Rebuildable Derived Indices**: OpenSearch and Qdrant hold derived index data only. If either database is cleared, the system can completely re-index all content from Postgres.
3. **Local Container Binding**: Containers bind exclusively to `127.0.0.1`. No external ports are published to public interfaces.
4. **Untrusted Data Isolation**: Crawled web pages and uploaded files are treated purely as data. Any embedded prompt injection attempts are sanitized prior to ingestion and indexing.

---

## 📜 License

MIT License — see [LICENSE](./LICENSE) for details.
