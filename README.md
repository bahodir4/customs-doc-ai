# customs-doc-ai

Local AI document intelligence platform for Uzbekistan customs documents
(invoices, AWB, GTD, CMR, packing lists). Fully self-hosted — no external APIs.

## Stack

- **LLM**: Qwen 2.5 via Ollama
- **Embeddings**: BGE-M3 (multilingual UZ / RU / EN)
- **Vector store**: Qdrant
- **Database**: PostgreSQL (async)
- **Orchestration**: LangGraph + LangChain
- **OCR**: PaddleOCR + PyMuPDF
- **UI**: Streamlit

## Phase 1 — Infrastructure setup

### 1. Prerequisites

- Docker Engine 24+ and Docker Compose v2
- Python 3.11+
- ~10 GB free disk (for models and Postgres data)

### 2. Bootstrap

```bash
git clone <repo-url> customs-doc-ai
cd customs-doc-ai

# Configuration
cp .env.example .env

# Python environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Infrastructure
docker compose up -d

# Pull models (first run only — downloads ~10 GB)
docker exec customs-ollama ollama pull qwen2.5:7b
docker exec customs-ollama ollama pull bge-m3

# Verify everything is healthy
python scripts/verify_services.py
```

Expected output:

```
Checking infrastructure services...

  [OK] Qdrant       reachable at http://localhost:6333
  [OK] PostgreSQL   PostgreSQL 16.x
  [OK] Ollama       2 model(s): qwen2.5:7b, bge-m3

All services healthy.
```

### 3. Project layout

```
customs-doc-ai/
├── config/      # Pydantic settings
├── core/        # Services, schemas, prompts, pipelines
├── rag/         # lex.uz knowledge base
├── app/         # Streamlit UI
├── scripts/     # CLI utilities
├── tests/       # Unit & integration tests
└── data/        # Docker volumes (gitignored)
```

## Phase 2 — Core services

Four independent, async, dependency-injected service classes:

| Service | Responsibility |
|---|---|
| `OCRService` | Smart PDF text extraction with PaddleOCR fallback for scans |
| `LLMService` | Qwen / Ollama wrapper: `complete`, `complete_json`, `detect_language`, `detect_intent`, `chat` |
| `VectorStoreService` | Async Qdrant client with two collections (`doc_chunks`, `lex_uz`) |
| `DBService` | Async SQLAlchemy persistence for processed documents |

### Initialise the database

```bash
python scripts/init_db.py
```

### Run the smoke tests

```bash
# Unit-style tests only (no services needed) — 8 tests, ~50 ms
pytest

# Full smoke suite (requires Qdrant, Postgres, Ollama up) — 28 tests
pytest --run-integration -v
```

## Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Infrastructure & scaffolding | done |
| 2 | Core services (OCR, LLM, vector, DB) | done |
| 3 | Schemas & prompts | pending |
| 4 | LangGraph pipelines | pending |
| 5 | lex.uz RAG ingestion | pending |
| 6 | Streamlit UI | pending |
| 7 | Hardening & demo | pending |
