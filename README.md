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

## Platform notes

### Apple Silicon (M1 / M2 / M3 Mac) — recommended setup

Running Ollama inside Docker on Mac is **not recommended** for two reasons:

1. **Memory** — Docker Desktop's VM is capped (8 GB by default). A 7B model
   needs ~6 GB of weights plus ~2 GB of KV cache, leaving nothing for
   Qdrant + Postgres. You will see `llama-server process has terminated:
   signal: killed` — the OS OOM killer at work.
2. **GPU** — Docker on Mac has no access to Apple's Metal GPU. Inference
   runs CPU-only and is ~5x slower than native.

**Recommended: run Ollama natively, keep Qdrant + Postgres in Docker.**

```bash
# 1. Stop the Dockerised Ollama (if it was started before)
docker compose stop ollama
docker compose rm -f ollama

# 2. Install native Ollama
brew install ollama
brew services start ollama   # auto-starts on boot

# 3. Pull models (same names, faster download via Metal-aware Ollama)
ollama pull qwen2.5:7b
ollama pull bge-m3

# 4. Verify — the code calls localhost:11434 either way, no changes needed
python scripts/verify_services.py
```

If you want to keep Ollama in Docker, raise Docker Desktop's memory limit
to **at least 12 GB** (Settings → Resources → Memory) and use a smaller
model like `qwen2.5:3b` (1.9 GB) by setting `OLLAMA_CHAT_MODEL=qwen2.5:3b`
in your `.env`.

### Linux / Windows

The default `docker compose up -d` is fine — all three services run in
containers without issue.

## Phase 3 — Schemas & prompts

Pydantic schemas and extraction prompts for every supported document type:

| Doc type | Schema | Prompt | Mandatory field |
|---|---|---|---|
| `invoice` | `InvoiceSchema` (nested seller/buyer/line_items/bank) | `invoice_prompt` | `invoice_number` |
| `awb` | `AWBSchema` | `awb_prompt` | `awb_number` |
| `gtd` | `GTDSchema` (with `GTDLineItem`) | `gtd_prompt` | `declaration_number` |
| `cmr` | `CMRSchema` | `cmr_prompt` | `cmr_number` |
| `packing_list` | `PackingListSchema` (with `PackageItem`) | `packing_list_prompt` | `packing_list_number` |

Plus a `classify` prompt that maps raw OCR text → one of `invoice / awb / gtd / cmr / packing_list / letter / unknown`.

### Try extraction end-to-end

```bash
# Auto-classify then extract
python scripts/extract_sample.py tests/samples/invoice.pdf

# Skip classification and force a doc type
python scripts/extract_sample.py tests/samples/awb.jpg --type awb

# Write JSON to a file instead of stdout
python scripts/extract_sample.py tests/samples/gtd.jpg -o gtd.json
```

### Run the Phase 3 tests

```bash
# 55 unit tests (Pydantic + prompt registry) — ~0.1 s, no LLM needed
pytest tests/test_schemas.py tests/test_prompts.py -v

# 4 end-to-end integration tests (classify + extract roundtrips)
pytest tests/test_extraction.py --run-integration -v
```

## Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Infrastructure & scaffolding | done |
| 2 | Core services (OCR, LLM, vector, DB) | done |
| 3 | Schemas & prompts | done |
| 4 | LangGraph pipelines | pending |
| 5 | lex.uz RAG ingestion | pending |
| 6 | Streamlit UI | pending |
| 7 | Hardening & demo | pending |
