"""Bulk ingestion workflow: originals dir → markdown dir → vector store → cleanup.

Drop `.docx` (or `.md`) files into `originals_dir`, run the workflow, and
each file is independently:

1. Converted to markdown and written into `markdown_dir`.
2. Ingested into the `lex_uz` Qdrant collection.
3. On success → both the original AND the converted MD are deleted.
   On failure → both remain in place for inspection.

Per-file atomicity means re-running after a partial failure cleanly
retries only the failed files. Successful files are already gone, so
they won't be re-ingested.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol

from core.logging import get_logger
from rag.loaders import DocxLoader, MarkdownFileLoader

logger = get_logger(__name__)

_SUPPORTED_SOURCE_EXTS: Final[frozenset[str]] = frozenset({
    ".docx", ".md", ".markdown", ".txt"
})


@dataclass(frozen=True, slots=True)
class FileResult:
    """Outcome of processing a single file."""

    source: Path
    status: str                       # "ok" | "failed" | "skipped"
    markdown_path: Path | None = None
    chunks_written: int = 0
    error: str | None = None
    deleted: bool = False


@dataclass(frozen=True, slots=True)
class WorkflowSummary:
    """Aggregate result of a workflow run."""

    results: list[FileResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.results if r.status == "ok")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "failed")

    @property
    def total_chunks(self) -> int:
        return sum(r.chunks_written for r in self.results)


class IngestService(Protocol):
    """Minimal contract the workflow needs from the ingestion service."""

    async def ingest(self, source: str | Path):  # noqa: D401 — protocol stub
        ...


class BulkIngestWorkflow:
    """End-to-end: discover sources, convert to markdown, ingest, clean up."""

    def __init__(
        self,
        originals_dir: Path,
        markdown_dir: Path,
        ingest_service: IngestService,
        *,
        delete_after_success: bool = True,
        docx_loader: DocxLoader | None = None,
        md_loader: MarkdownFileLoader | None = None,
    ) -> None:
        self._originals = originals_dir
        self._markdown = markdown_dir
        self._service = ingest_service
        self._delete = delete_after_success
        self._docx_loader = docx_loader or DocxLoader()
        self._md_loader = md_loader or MarkdownFileLoader()

    # ── Public API ───────────────────────────────────────────────────

    def ensure_directories(self) -> None:
        """Create both working directories if they don't exist."""
        self._originals.mkdir(parents=True, exist_ok=True)
        self._markdown.mkdir(parents=True, exist_ok=True)

    def discover_sources(self) -> list[Path]:
        """Find all supported files in `originals_dir` (non-recursive)."""
        if not self._originals.exists():
            return []
        return sorted(
            p for p in self._originals.iterdir()
            if p.is_file() and p.suffix.lower() in _SUPPORTED_SOURCE_EXTS
        )

    async def process_one(self, source: Path) -> FileResult:
        """Convert + ingest + (optionally) delete a single file."""
        md_path: Path | None = None
        try:
            md_path = await self._convert_to_markdown(source)
            logger.info("Converted %s → %s", source.name, md_path.name)

            result = await self._service.ingest(md_path)
            chunks = getattr(result, "chunks_written", 0)
            logger.info("Ingested %d chunk(s) from %s", chunks, source.name)

            if chunks <= 0:
                return FileResult(
                    source=source,
                    status="failed",
                    markdown_path=md_path,
                    error="0 chunks ingested",
                )

            deleted = False
            if self._delete:
                self._delete_file(source)
                self._delete_file(md_path)
                deleted = True
                logger.info("Deleted %s and %s", source.name, md_path.name)

            return FileResult(
                source=source,
                status="ok",
                markdown_path=md_path,
                chunks_written=chunks,
                deleted=deleted,
            )
        except Exception as exc:
            logger.exception("Failed to process %s", source.name)
            # Leave both files in place for inspection.
            return FileResult(
                source=source,
                status="failed",
                markdown_path=md_path,
                error=f"{type(exc).__name__}: {exc}",
            )

    async def run(self) -> WorkflowSummary:
        """Process every file in `originals_dir`, return aggregate summary."""
        self.ensure_directories()
        sources = self.discover_sources()

        if not sources:
            logger.warning("No source files found in %s", self._originals)
            return WorkflowSummary(results=[])

        logger.info("Discovered %d source file(s)", len(sources))
        results: list[FileResult] = []
        for source in sources:
            result = await self.process_one(source)
            results.append(result)
        return WorkflowSummary(results=results)

    # ── Internals ────────────────────────────────────────────────────

    async def _convert_to_markdown(self, source: Path) -> Path:
        """Convert any supported source to markdown, write into markdown_dir."""
        suffix = source.suffix.lower()
        if suffix == ".docx":
            md_text = await self._docx_loader.load(str(source))
        elif suffix in (".md", ".markdown", ".txt"):
            md_text = await self._md_loader.load(str(source))
        else:
            raise ValueError(f"Unsupported source type: {suffix!r}")

        md_path = self._markdown / (source.stem + ".md")
        md_path.write_text(md_text, encoding="utf-8")
        return md_path

    @staticmethod
    def _delete_file(path: Path) -> None:
        """Delete a file, silently ignoring 'already gone' errors."""
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not delete %s: %s", path, exc)
