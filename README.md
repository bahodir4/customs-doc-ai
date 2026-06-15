# customs-doc-ai

Self-hosted AI platform for Uzbekistan customs document processing and law retrieval.
Processes trade documents (invoices, AWBs, GTDs, CMRs, packing lists), corrects OCR errors,
evaluates scan quality, extracts structured data, and answers questions in Uzbek, Russian, and English —
all running locally with no external API calls required.

---

## Stack

| Layer | Technology |
|---|---|
| LLM | Ollama (default: `qwen2.5:7b`) or OpenAI (`gpt-4.1-mini`) |
| Embeddings | `bge-m3` via Ollama — multilingual UZ / RU / EN |
| Vector store | Qdrant (two collections: `doc_chunks`, `lex_uz`) |
| Structured store | PostgreSQL 16 via async SQLAlchemy + asyncpg |
| Orchestration | LangGraph state machines + LangChain |
| OCR | PyMuPDF (native text) with PaddleOCR fallback for scans |
| UI | Streamlit 1.36+ |

---

## Quick start

### Prerequisites

- Docker Engine 24+ and Docker Compose v2
- Python 3.11+
- ~10 GB free disk (models + Postgres data)
- macOS/Linux (Windows via WSL2)

### 1. Clone and configure

```bash
git clone <repo-url> customs-doc-ai
cd customs-doc-ai

cp .env.example .env          # edit if needed (defaults work for local dev)

python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Start infrastructure

```bash
docker compose up -d          # starts Qdrant + PostgreSQL
```

> **Apple Silicon (M1/M2/M3):** run Ollama natively for Metal GPU acceleration:
> ```bash
> brew install ollama && brew services start ollama
> ```
> On Linux/Windows the Docker-bundled Ollama works fine. Either way, raise Docker Desktop
> memory to at least 12 GB (Settings → Resources → Memory) if keeping Ollama in Docker.

### 3. Pull models

```bash
ollama pull qwen2.5:7b        # LLM (~4.7 GB)
ollama pull bge-m3            # embeddings (~1.2 GB)
```

### 4. Initialise and verify

```bash
python scripts/init_db.py         # create PostgreSQL tables (run once)
python scripts/verify_services.py # confirm Qdrant, Postgres, Ollama are healthy
```

Expected output:
```
[OK] Qdrant       reachable at http://localhost:6333
[OK] PostgreSQL   PostgreSQL 16.x
[OK] Ollama       2 model(s): qwen2.5:7b, bge-m3
All services healthy.
```

### 5. Launch the UI

```bash
streamlit run streamlit_app.py
```

Open `http://localhost:8501`.

---

## Document processing pipeline

Every uploaded document passes through a 7-stage LangGraph pipeline:

```
load → ocr → correct → quality → classify → extract → store
```

| Stage | What happens |
|---|---|
| **load** | Validate file exists, detect type (pdf / jpg / png / docx) |
| **ocr** | PyMuPDF extracts native text; PaddleOCR used as fallback for scanned images |
| **correct** | LLM fixes OCR errors: character substitutions (`v1EDICAL→MEDICAL`), broken words, garbled Cyrillic/Latin noise, stamp/signature artefacts — without adding or translating content |
| **quality** | LLM rates corrected text as `GOOD` / `DEGRADED` / `UNREADABLE`, reports readable %, and lists detected issue types (`garbled_words`, `broken_numbers`, `character_subs`, etc.) |
| **classify** | LLM classifies into `invoice / awb / gtd / cmr / packing_list / letter / unknown` |
| **extract** | Schema-free LLM extraction into structured JSON sections (`references`, `parties`, `goods`, `financials`, `logistics`, `customs`). Multi-page docs use map-reduce: full-text for headers, per-page parallel calls for line items. All values copied verbatim — no paraphrasing. |
| **store** | Save to PostgreSQL + embed OCR text chunks into Qdrant `doc_chunks`. OCR quality metadata stored inside `extracted_data._ocr_quality`. |

Errors in any node set `status="error"` and short-circuit downstream nodes, but `store` always runs so a record exists for inspection.

---

## Chat agent

```
detect_language → detect_intent → [route] → respond
                                      │
                                      ├── doc_qa  → PostgreSQL + doc_chunks
                                      ├── rag     → lex_uz law collection
                                      └── hybrid  → all three sources
```

- Detects language (uz / ru / en) and routes by intent automatically.
- Answers grounded in retrieved context only — no hallucination from training data.
- Real-time token streaming via async queue bridge (no page freeze during generation).
- Responses include language, intent, and source indicators.

---

## Knowledge base (lex_uz)

Ingests Uzbek customs law and regulations into the `lex_uz` Qdrant collection for RAG retrieval.

**Supported sources:** URLs, `.docx`, `.md`, `.txt`

**Ingestion pipeline:**

```
fetch/load → convert to markdown → clean OCR noise → hierarchical chunk → embed (BGE-M3) → store
```

**Chunking strategy:** `HierarchicalChunker` splits at `#` / `##` boundaries. Each chunk's text is prefixed with its full header breadcrumb (`# Customs Code\n## Article 5\n\n...`) so the embedding captures section context. Sub-chunks inherit parent headers.

**Markdown backup:** Every ingestion saves the converted markdown to `docs/lex_uz/converted/` for inspection — this lets you verify the conversion quality before chunks go into the vector store.

> **lex.uz note:** lex.uz pages are JavaScript-rendered; the URL loader will not extract content correctly. Export the DOCX from lex.uz and upload that instead.

---

## UI pages

| Page | Description |
|---|---|
| 💬 **Chat** | Streaming chat with scope filter (all docs or specific IDs), health status sidebar, language/intent/source metadata after each answer |
| 📄 **Documents** | Upload PDF/DOCX/JPG/PNG; real-time 7-stage pipeline progress per file; OCR quality badge + warning banner for DEGRADED/UNREADABLE docs; extracted data in Fields and Raw JSON tabs; export as JSON / Excel / CSV; delete |
| 📚 **Knowledge Base** | Ingest URL or file with real-time stage progress; bulk workflow for multiple DOCX files; view converted markdown backups; manage ingested sources; wipe collection |
| ⚙️ **Settings** | Connection health metrics for Ollama / Qdrant / PostgreSQL; collection stats; database management |

---

## Project layout

```
customs-doc-ai/
├── streamlit_app.py            # Chat page — default entry point
├── pages/
│   ├── 2_📄_Documents.py       # Document upload + management
│   ├── 3_📚_Knowledge_Base.py  # KB ingestion + inspection
│   └── 4_⚙️_Settings.py       # Health checks + DB management
│
├── app/
│   ├── async_runner.py         # Single background event loop bridge (run_async / stream_async)
│   ├── services.py             # @st.cache_resource singletons + streaming generators
│   ├── components.py           # Reusable UI: badges, doc cards, sidebar, health pills
│   ├── styles.py               # CSS design system (dark sidebar, card layout, tags)
│   └── document_export.py      # JSON / multi-sheet Excel / CSV export helpers
│
├── core/
│   ├── pipeline/
│   │   ├── doc_pipeline.py     # 7-stage LangGraph doc processing graph
│   │   ├── chat_agent.py       # Chat + retrieval-only LangGraph graphs
│   │   └── state.py            # TypedDict state definitions for both graphs
│   ├── prompts/
│   │   ├── correct.py          # OCR correction prompt
│   │   ├── quality.py          # OCR quality assessment prompt
│   │   ├── classify.py         # Document type classification prompt
│   │   └── organize.py         # Schema-free structured extraction prompt
│   ├── services/
│   │   ├── ocr_service.py      # PyMuPDF + PaddleOCR with smart fallback
│   │   ├── llm_service.py      # Ollama / OpenAI wrapper (complete, complete_json, astream_chat)
│   │   ├── vector_store.py     # Qdrant async client (doc_chunks + lex_uz collections)
│   │   └── db_service.py       # Async SQLAlchemy PostgreSQL persistence
│   └── schemas/                # Pydantic schemas (AWB, GTD, CMR, Invoice, PackingList)
│
├── rag/
│   ├── loaders.py              # URLLoader, DocxLoader, MarkdownFileLoader
│   ├── chunking.py             # HierarchicalChunker (header split + size split)
│   ├── ingestion.py            # LexIngestionService with progress callbacks
│   └── bulk_ingest.py          # BulkIngestWorkflow for batch DOCX processing
│
├── config/
│   └── settings.py             # Pydantic-settings with per-service env prefix
│
├── scripts/
│   ├── init_db.py              # Create PostgreSQL tables (run once on setup)
│   ├── verify_services.py      # Health check: Qdrant + Postgres + Ollama
│   ├── process_document.py     # CLI: run full pipeline on a file
│   ├── chat_with_docs.py       # CLI: ask the chat agent a question
│   ├── ingest_lex.py           # CLI: ingest one or more sources into lex_uz
│   ├── ingest_lex_docs.py      # CLI: bulk ingest from docs/lex_uz/originals/
│   └── clear_lex.py            # CLI: wipe and recreate the lex_uz collection
│
├── tests/                      # Unit + integration tests (pytest)
├── docs/
│   ├── lex_uz/
│   │   ├── originals/          # Drop DOCX files here for bulk ingestion
│   │   ├── converted/          # Markdown backups saved after each ingestion
│   │   └── markdown/           # Intermediate markdown staging (bulk workflow)
│   └── sample_files/           # Sample customs documents for testing
│
├── docker-compose.yml          # Qdrant + PostgreSQL (+ optional Ollama)
├── .env.example                # All configurable environment variables
└── requirements.txt
```

---

## Configuration

All settings are read from `.env` (copy from `.env.example`). Key variables:

```env
# LLM provider: "ollama" (local, default) or "openai"
LLM_PROVIDER=ollama

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=qwen2.5:7b
OLLAMA_EMBED_MODEL=bge-m3

# OpenAI (used only when LLM_PROVIDER=openai)
OPENAI_API_KEY=
OPENAI_CHAT_MODEL=gpt-4.1-mini

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=custdocs

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333

# RAG chunking
RAG_CHUNK_SIZE=500
RAG_CHUNK_OVERLAP=50
RAG_TOP_K=5
```

---

## CLI scripts

```bash
# First-time setup
python scripts/init_db.py
python scripts/verify_services.py

# Process a document (saves to Postgres + Qdrant)
python scripts/process_document.py "docs/sample_files/invoice.pdf"

# Chat from the terminal
python scripts/chat_with_docs.py "What is the customs duty on medical devices?"
python scripts/chat_with_docs.py "Какова сумма счёта?" --doc-ids <doc_id>

# Ingest customs law
python scripts/ingest_lex.py docs/lex_uz/originals/customs_code.docx
python scripts/ingest_lex_docs.py   # bulk: processes all files in docs/lex_uz/originals/

# Wipe and re-ingest
python scripts/clear_lex.py && python scripts/ingest_lex_docs.py
```

---

## Tests

```bash
# Fast unit tests — no services needed (~1 s)
pytest

# Full integration suite — requires Qdrant + Postgres + Ollama
pytest --run-integration -v
```

---

## OCR quality ratings

Documents are automatically evaluated after OCR correction:

| Rating | Meaning | UI indicator |
|---|---|---|
| **GOOD** | < 5% noise, all fields reliably readable | No banner |
| **DEGRADED** | 5–35% noise, main content recoverable but numeric fields need verification | ⚠️ Amber warning banner |
| **UNREADABLE** | > 35% noise, critical fields (amounts, dates, references) are corrupted | 🚨 Red warning banner |

For DEGRADED/UNREADABLE documents: re-scan at higher DPI, or if the document originated digitally, obtain the DOCX/PDF source instead of a scan.
