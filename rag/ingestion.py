"""Customs-law ingestion service.

The public surface is `LexIngestionService.ingest(source)` which accepts
any of:

- a URL (`http://` / `https://`)
- a `.docx` file path
- a `.md` or `.txt` file path

It runs the appropriate loader, hands the markdown to
`HierarchicalChunker`, and writes the chunks (with hierarchical metadata)
into the `lex_uz` Qdrant collection. The chat agent already searches
that collection via `VectorStoreService.search_lex()` — no changes
required there.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import settings
from core.logging import get_logger
from core.services import VectorStoreService
from rag.chunking import HierarchicalChunker
from rag.loaders import DocxLoader, MarkdownFileLoader, URLLoader

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Outcome of a single ingest call."""

    source: str
    source_type: str          # "url" | "docx" | "markdown"
    raw_markdown_chars: int
    chunks_written: int


class UnsupportedSourceError(ValueError):
    """Raised for source types we cannot ingest."""


class LexIngestionService:
    """Ingest URLs and files into the lex_uz collection."""

    _DOCX_EXTS = frozenset({".docx"})
    _MARKDOWN_EXTS = frozenset({".md", ".markdown", ".txt"})

    def __init__(
        self,
        vector_store: VectorStoreService,
        chunker: HierarchicalChunker | None = None,
        url_loader: URLLoader | None = None,
        docx_loader: DocxLoader | None = None,
        md_loader: MarkdownFileLoader | None = None,
    ) -> None:
        self._vector = vector_store
        self._chunker = chunker or HierarchicalChunker(
            chunk_size=settings.rag.chunk_size,
            chunk_overlap=settings.rag.chunk_overlap,
        )
        self._url_loader = url_loader or URLLoader()
        self._docx_loader = docx_loader or DocxLoader()
        self._md_loader = md_loader or MarkdownFileLoader()

    # ── Public API ──────────────────────────────────────────────────

    async def ingest(self, source: str | Path) -> IngestionResult:
        """Auto-detect source type and ingest."""
        source_str = str(source)

        if self._is_url(source_str):
            return await self._ingest_url(source_str)

        path = Path(source_str)
        if not path.exists():
            raise FileNotFoundError(f"Source not found: {path}")

        suffix = path.suffix.lower()
        if suffix in self._DOCX_EXTS:
            return await self._ingest_docx(path)
        if suffix in self._MARKDOWN_EXTS:
            return await self._ingest_markdown_file(path)

        raise UnsupportedSourceError(
            f"Unsupported source type: {suffix!r}. "
            f"Use a URL, .docx, .md, or .txt."
        )

    async def ingest_markdown_text(
        self, markdown: str, source: str = "<inline>"
    ) -> IngestionResult:
        """Ingest a markdown string directly (no loader needed)."""
        return await self._ingest_markdown_body(
            markdown=markdown,
            source=source,
            source_type="markdown",
        )

    # ── Source-type handlers ────────────────────────────────────────

    async def _ingest_url(self, url: str) -> IngestionResult:
        markdown = await self._url_loader.load(url)
        return await self._ingest_markdown_body(
            markdown=markdown, source=url, source_type="url"
        )

    async def _ingest_docx(self, path: Path) -> IngestionResult:
        markdown = await self._docx_loader.load(str(path))
        return await self._ingest_markdown_body(
            markdown=markdown,
            source=str(path.resolve()),
            source_type="docx",
        )

    async def _ingest_markdown_file(self, path: Path) -> IngestionResult:
        markdown = await self._md_loader.load(str(path))
        return await self._ingest_markdown_body(
            markdown=markdown,
            source=str(path.resolve()),
            source_type="markdown",
        )

    # ── Core ingest ─────────────────────────────────────────────────

    async def _ingest_markdown_body(
        self,
        markdown: str,
        source: str,
        source_type: str,
    ) -> IngestionResult:
        if not markdown.strip():
            logger.warning("Empty markdown — nothing to ingest from %s", source)
            return IngestionResult(
                source=source,
                source_type=source_type,
                raw_markdown_chars=0,
                chunks_written=0,
            )

        logger.info(
            "Ingesting %s (%s, %d chars of markdown)",
            source, source_type, len(markdown),
        )

        chunks = self._chunker.chunk(markdown, source=source)
        if not chunks:
            logger.warning("Chunker produced 0 chunks for %s", source)
            return IngestionResult(
                source=source,
                source_type=source_type,
                raw_markdown_chars=len(markdown),
                chunks_written=0,
            )

        await self._vector.ensure_collections()
        count = await self._vector.upsert_lex_chunks(
            chunks=[c.text for c in chunks],
            metadatas=[c.to_metadata() for c in chunks],
        )
        logger.info("Upserted %d chunks from %s", count, source)

        return IngestionResult(
            source=source,
            source_type=source_type,
            raw_markdown_chars=len(markdown),
            chunks_written=count,
        )

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _is_url(source: str) -> bool:
        return source.lower().startswith(("http://", "https://"))
