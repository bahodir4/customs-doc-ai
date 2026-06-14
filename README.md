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

## Phase 4 — LangGraph pipelines

Two compiled state machines that orchestrate Phase 2 services + Phase 3
prompts/schemas:

### Document processing pipeline

```
load → ocr → classify → extract → validate → store
```

- Linear flow, async throughout, services injected via closure.
- Error-guard pattern: failure in any node sets `status="error"`; downstream
  nodes short-circuit, but `store` always runs so a record exists for inspection.
- Embeds OCR text into Qdrant `doc_chunks` after successful save.

### Chat agent graph

```
detect_language → detect_intent → [route by intent] → respond
                                       │
                                       ├── doc_qa  → retrieve_doc_qa
                                       ├── rag     → retrieve_rag
                                       └── hybrid  → retrieve_hybrid
```

- Conditional routing on the detected intent picks one of three retrieval
  strategies: PostgreSQL + doc_chunks, lex_uz only, or all three sources.
- Single `respond` node receives any path and generates the answer in
  the user's detected language.

### Run the pipelines

```bash
# Process a document end-to-end (writes to Postgres + Qdrant)
python scripts/process_document.py "docs/sample_files/Final INVOICES .pdf"

# Ask the chat agent a question
python scripts/chat_with_docs.py "What is the duty on medical devices?"
python scripts/chat_with_docs.py "Какова сумма счёта?" --doc-ids <doc_id>
```

### Run the Phase 4 tests

```bash
# 12 pure-unit tests (graph helpers + context builders) — ~0.1 s
pytest tests/test_doc_pipeline.py tests/test_chat_agent.py -v

# 5 integration tests (full pipelines against live services)
pytest tests/test_doc_pipeline.py tests/test_chat_agent.py --run-integration -v
```

## Phase 5 — RAG ingestion (URL / DOCX / Markdown)

Smart hierarchical ingestion into the `lex_uz` Qdrant collection.

### Input formats

| Type | Loader | How |
|---|---|---|
| URL  | `URLLoader` | httpx fetch + strip nav/footer/scripts + `markdownify` ATX headings |
| DOCX | `DocxLoader` | `python-docx` walks paragraphs; styles `Heading 1/2/3` and `Заголовок 1/2/3` map to `#/##/###` |
| MD/TXT | `MarkdownFileLoader` | Pass-through |

### Smart chunking strategy

Two-stage chunking in `HierarchicalChunker`:

1. **Header split** — `MarkdownHeaderTextSplitter` carves the document at
   `#`, `##`, `###` boundaries, each piece tagged with its header path.
2. **Size split** — sections over ~1.5× chunk_size are sub-split by
   `RecursiveCharacterTextSplitter`; sub-chunks inherit parent headers.

**Key trick:** each chunk's text starts with its full header path
(`# Customs Code\n## Article 5: Medical Devices\n\n...body...`) so the
embedding carries section context. A query about "Article 5" matches even
if the body itself doesn't repeat the article number.

Metadata stored alongside the vector:
- `h1`, `h2`, `h3` — heading hierarchy
- `breadcrumb` — `"Customs Code > Article 5: Medical Devices"`
- `source` — original URL or file path
- `chunk_index` — position within the source

### Ingest content

**Option A — bulk workflow with cleanup (recommended for lex.uz DOCX downloads):**

```bash
# 1. Download .docx files from lex.uz manually and drop them in:
#    docs/lex_uz/originals/
#
# 2. Run the bulk workflow:
python scripts/ingest_lex_docs.py
```

For each file, the workflow will:
1. Convert it to markdown (saved to `docs/lex_uz/markdown/`)
2. Ingest into the `lex_uz` Qdrant collection (with hierarchical chunking)
3. **On success**, delete both the original and the converted MD
4. **On failure**, leave both files in place for inspection

This means partial failures are recoverable — just re-run after fixing whatever
broke; only failed files get retried.

Flags:
- `--no-delete` — keep both files even after successful ingest (debugging)
- `--originals-dir PATH` — custom source directory
- `--markdown-dir PATH` — custom staging directory

**Option B — one-shot from arbitrary source (URL / DOCX / MD / TXT):**

```bash
# Single URL
python scripts/ingest_lex.py https://lex.uz/docs/3062271

# Multiple sources, mixed
python scripts/ingest_lex.py \
    docs/customs_code.docx \
    notes/medical_devices.md \
    https://some-static-site.example.com/article
```

(Note: lex.uz pages are JavaScript-rendered so the URL path won't extract
the actual customs text — use the DOCX export and Option A instead.)

**Wipe and re-ingest:**

```bash
python scripts/clear_lex.py
python scripts/ingest_lex_docs.py
```

### Test the chat agent against ingested content

```bash
python scripts/chat_with_docs.py "What is the customs duty on medical devices?"
python scripts/chat_with_docs.py "Какова ставка пошлины на код 3822?"
```

The chat agent (Phase 4) automatically picks up the ingested content via
`VectorStoreService.search_lex()` — no code changes needed.

### Run the Phase 5 tests

```bash
# 30 unit tests (chunking + loaders + dispatch) — ~1 s, no LLM needed
pytest tests/test_rag_chunking.py tests/test_rag_loaders.py tests/test_rag_ingestion.py -v

# 4 integration tests (full ingestion + search round-trip)
pytest tests/test_rag_ingestion.py --run-integration -v
```

## Phase 6 — Streamlit UI

A modern chat-app UI on top of all the previous phases.

### Running it

```bash
streamlit run streamlit_app.py
```

Open `http://localhost:8501` in a browser.

### Pages

| Page | What it does |
|---|---|
| 💬 **Chat** (default) | ChatGPT-style chat with message bubbles, document-scope filter in sidebar, live system-status pills, language/intent/source indicators after each answer. |
| 📄 **Documents** | Drag-and-drop upload (PDF/JPG/PNG), step-by-step pipeline status per file, per-document Fields & Raw JSON tabs, **JSON + Excel download buttons**, delete. |
| 📚 **Knowledge Base** | Ingest single URL or file, run the bulk DOCX → markdown → ingest workflow (with auto-cleanup), wipe the lex_uz collection. |

### "Smart" Excel export

Each document downloads as a multi-sheet `.xlsx`:

- **Document** sheet: flat `Field / Value` table with nested objects flattened via dot-notation (e.g. `seller.name`, `seller.country`).
- **Line Items / Items** sheet (etc.): one sheet per list-valued field, one row per item, with the inner dict columns expanded.
- Bold header row, auto-fit column widths, frozen top row.

### Architecture

```
streamlit_app.py        # Chat page (default entry point)
pages/
├── 2_📄_Documents.py
└── 3_📚_Knowledge_Base.py
app/
├── async_runner.py     # one persistent event loop for asyncpg/httpx/qdrant
├── services.py         # @st.cache_resource singletons of services + pipelines
├── styles.py           # custom CSS (typography, chat bubbles, file uploader, etc.)
├── components.py       # reusable UI: status pills, empty states, badges
└── document_export.py  # JSON + multi-sheet Excel helpers (pure logic, tested)
```

The async clients (Ollama, Qdrant, asyncpg) all live on one persistent event loop kept alive via `@st.cache_resource`, so they survive Streamlit's per-interaction reruns without cross-loop errors.

## Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Infrastructure & scaffolding | done |
| 2 | Core services (OCR, LLM, vector, DB) | done |
| 3 | Schemas & prompts | done |
| 4 | LangGraph pipelines | done |
| 5 | RAG ingestion (URL / DOCX / MD + bulk workflow) | done |
| 6 | Streamlit UI | done |
| 7 | Hardening & demo | pending |
