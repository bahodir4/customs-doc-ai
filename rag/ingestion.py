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

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

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
        markdown_backup_dir: Path | None = None,
    ) -> None:
        self._vector = vector_store
        self._chunker = chunker or HierarchicalChunker(
            chunk_size=settings.rag.chunk_size,
            chunk_overlap=settings.rag.chunk_overlap,
        )
        self._url_loader = url_loader or URLLoader()
        self._docx_loader = docx_loader or DocxLoader()
        self._md_loader = md_loader or MarkdownFileLoader()
        if markdown_backup_dir is not None:
            markdown_backup_dir.mkdir(parents=True, exist_ok=True)
        self._backup_dir = markdown_backup_dir

    # ── Public API ──────────────────────────────────────────────────

    async def ingest(
        self,
        source: str | Path,
        progress_callback: Callable[[str, Any], None] | None = None,
    ) -> IngestionResult:
        """Auto-detect source type and ingest.

        ``progress_callback`` is called with ``(stage, data)`` at each step:
        ``converting`` → ``converted`` → ``chunking`` → ``chunked`` →
        ``embedding`` → ``stored``.  Thread-safe: called from the event loop.
        """
        source_str = str(source)

        if self._is_url(source_str):
            return await self._ingest_url(source_str, progress_callback)

        path = Path(source_str)
        if not path.exists():
            raise FileNotFoundError(f"Source not found: {path}")

        suffix = path.suffix.lower()
        if suffix in self._DOCX_EXTS:
            return await self._ingest_docx(path, progress_callback)
        if suffix in self._MARKDOWN_EXTS:
            return await self._ingest_markdown_file(path, progress_callback)

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

    async def _ingest_url(self, url: str, cb=None) -> IngestionResult:
        if cb:
            cb("converting", {"type": "url", "source": url})
        markdown = await self._url_loader.load(url)
        if cb:
            cb("converted", {"chars": len(markdown)})
        return await self._ingest_markdown_body(markdown, url, "url", cb)

    async def _ingest_docx(self, path: Path, cb=None) -> IngestionResult:
        if cb:
            cb("converting", {"type": "docx", "source": path.name})
        markdown = await self._docx_loader.load(str(path))
        if cb:
            cb("converted", {"chars": len(markdown)})
        return await self._ingest_markdown_body(markdown, str(path.resolve()), "docx", cb)

    async def _ingest_markdown_file(self, path: Path, cb=None) -> IngestionResult:
        if cb:
            cb("converting", {"type": "markdown", "source": path.name})
        markdown = await self._md_loader.load(str(path))
        if cb:
            cb("converted", {"chars": len(markdown)})
        return await self._ingest_markdown_body(markdown, str(path.resolve()), "markdown", cb)

    # ── Core ingest ─────────────────────────────────────────────────

    async def _ingest_markdown_body(
        self,
        markdown: str,
        source: str,
        source_type: str,
        cb: Callable[[str, Any], None] | None = None,
    ) -> IngestionResult:
        if not markdown.strip():
            logger.warning("Empty markdown — nothing to ingest from %s", source)
            return IngestionResult(
                source=source,
                source_type=source_type,
                raw_markdown_chars=0,
                chunks_written=0,
            )

        self._save_backup(markdown, source, source_type)

        logger.info(
            "Ingesting %s (%s, %d chars of markdown)",
            source, source_type, len(markdown),
        )

        if cb:
            cb("chunking", {})
        chunks = self._chunker.chunk(markdown, source=source)
        if cb:
            cb("chunked", {"count": len(chunks)})

        if not chunks:
            logger.warning("Chunker produced 0 chunks for %s", source)
            return IngestionResult(
                source=source,
                source_type=source_type,
                raw_markdown_chars=len(markdown),
                chunks_written=0,
            )

        if cb:
            cb("embedding", {"count": len(chunks)})
        await self._vector.ensure_collections()
        count = await self._vector.upsert_lex_chunks(
            chunks=[c.text for c in chunks],
            metadatas=[c.to_metadata() for c in chunks],
        )
        if cb:
            cb("stored", {"chunks_written": count})
        logger.info("Upserted %d chunks from %s", count, source)

        return IngestionResult(
            source=source,
            source_type=source_type,
            raw_markdown_chars=len(markdown),
            chunks_written=count,
        )

    # ── Helpers ─────────────────────────────────────────────────────

    def _save_backup(self, markdown: str, source: str, source_type: str) -> None:
        """Write markdown to the backup dir (if configured). Never raises."""
        if self._backup_dir is None:
            return
        try:
            filename = self._backup_filename(source, source_type)
            backup_path = self._backup_dir / filename
            backup_path.write_text(markdown, encoding="utf-8")
            logger.debug("Saved markdown backup → %s", backup_path)
        except Exception as exc:
            logger.warning("Could not write markdown backup for %s: %s", source, exc)

    @staticmethod
    def _backup_filename(source: str, source_type: str) -> str:
        """Derive a safe, unique filename for a markdown backup."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if source_type == "url":
            parsed = urlparse(source)
            slug = (parsed.netloc + parsed.path).strip("/").replace("/", "_")
            slug = re.sub(r"[^\w.-]", "_", slug)[:80]
            return f"{slug}__{ts}.md"
        stem = re.sub(r"[^\w.-]", "_", Path(source).stem)[:80]
        return f"{stem}__{ts}.md"

    @staticmethod
    def _is_url(source: str) -> bool:
        return source.lower().startswith(("http://", "https://"))
