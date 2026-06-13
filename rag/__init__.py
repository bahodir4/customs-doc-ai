"""RAG package — customs-law knowledge-base ingestion.

Three public entry points:
- `LexIngestionService.ingest(source)` — auto-detect URL / DOCX / MD and
  ingest into the `lex_uz` Qdrant collection (single source).
- `BulkIngestWorkflow` — orchestrate a folder of source files end-to-end
  (convert → ingest → cleanup).
- `HierarchicalChunker` — exposed for unit testing and reuse.

The chat agent already searches `lex_uz` via `VectorStoreService.search_lex()`,
so no changes are needed elsewhere once content is ingested.
"""
from rag.bulk_ingest import (
    BulkIngestWorkflow,
    FileResult,
    IngestService,
    WorkflowSummary,
)
from rag.chunking import HierarchicalChunker, LexChunk
from rag.ingestion import (
    IngestionResult,
    LexIngestionService,
    UnsupportedSourceError,
)
from rag.loaders import (
    DocxLoader,
    MarkdownFileLoader,
    MarkdownLoader,
    URLLoader,
)

__all__ = [
    "BulkIngestWorkflow",
    "DocxLoader",
    "FileResult",
    "HierarchicalChunker",
    "IngestService",
    "IngestionResult",
    "LexChunk",
    "LexIngestionService",
    "MarkdownFileLoader",
    "MarkdownLoader",
    "URLLoader",
    "UnsupportedSourceError",
    "WorkflowSummary",
]
