"""Bulk-ingest customs-law documents from a local directory.

Workflow:
1. Place .docx (or .md) files in docs/lex_uz/originals/
2. Run this script — for each file it will:
     a. Convert to markdown into docs/lex_uz/markdown/
     b. Ingest into the lex_uz Qdrant collection
     c. On success, delete BOTH the original and the converted MD
3. Failed files stay in place so you can inspect and re-run.

Examples:
    # Default workflow — convert, ingest, delete on success
    python scripts/ingest_lex_docs.py

    # Keep the files even after successful ingestion (debugging)
    python scripts/ingest_lex_docs.py --no-delete

    # Custom directories
    python scripts/ingest_lex_docs.py \\
        --originals-dir ~/Downloads/uz_law \\
        --markdown-dir /tmp/md_staging
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from core.logging import configure_logging, get_logger
from core.services import VectorStoreService
from rag import LexIngestionService
from rag.bulk_ingest import BulkIngestWorkflow, FileResult, WorkflowSummary

logger = get_logger(__name__)

DEFAULT_ORIGINALS_DIR: Path = settings.project_root / "docs" / "lex_uz" / "originals"
DEFAULT_MARKDOWN_DIR: Path = settings.project_root / "docs" / "lex_uz" / "markdown"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk-ingest customs-law DOCX/MD files into the lex_uz collection.",
    )
    parser.add_argument(
        "--originals-dir",
        type=Path,
        default=DEFAULT_ORIGINALS_DIR,
        help=f"Directory containing source files (default: {DEFAULT_ORIGINALS_DIR})",
    )
    parser.add_argument(
        "--markdown-dir",
        type=Path,
        default=DEFAULT_MARKDOWN_DIR,
        help=f"Directory for converted markdown (default: {DEFAULT_MARKDOWN_DIR})",
    )
    parser.add_argument(
        "--no-delete",
        action="store_true",
        help="Keep both original and converted files even after successful ingest.",
    )
    return parser.parse_args()


def _print_summary(summary: WorkflowSummary, *, originals_dir: Path) -> None:
    print()
    print("─" * 70)
    print(f"Files processed : {summary.total}")
    print(f"  succeeded     : {summary.succeeded}")
    print(f"  failed        : {summary.failed}")
    print(f"Total chunks    : {summary.total_chunks}")
    print()

    if summary.failed:
        print("Failures (files left in place for inspection):")
        for r in summary.results:
            if r.status == "failed":
                print(f"  • {r.source.name}: {r.error}")
        print()
        print(f"Source files retained in: {originals_dir}")


def _print_per_file(result: FileResult) -> None:
    if result.status == "ok":
        deleted = "deleted" if result.deleted else "kept"
        print(f"  [OK]   {result.source.name}: {result.chunks_written} chunks ({deleted})")
    else:
        print(f"  [FAIL] {result.source.name}: {result.error}")


async def main() -> int:
    args = _parse_args()
    configure_logging(settings.log_level)

    originals_dir: Path = args.originals_dir
    markdown_dir: Path = args.markdown_dir

    print(f"Originals dir : {originals_dir}")
    print(f"Markdown dir  : {markdown_dir}")
    print(f"Delete on OK  : {not args.no_delete}")
    print()

    # Build services
    vector = VectorStoreService(settings.qdrant, settings.ollama)
    ingest_service = LexIngestionService(vector_store=vector)

    workflow = BulkIngestWorkflow(
        originals_dir=originals_dir,
        markdown_dir=markdown_dir,
        ingest_service=ingest_service,
        delete_after_success=not args.no_delete,
    )

    try:
        # Pre-flight: warn if nothing to do.
        workflow.ensure_directories()
        sources = workflow.discover_sources()
        if not sources:
            print(f"No source files found in {originals_dir}.")
            print("Drop .docx (or .md) files there and re-run.")
            return 0

        print(f"Found {len(sources)} source file(s):")
        for s in sources:
            print(f"  • {s.name}")
        print()
        print("Processing...")
        print()

        # Run end-to-end, streaming per-file results to stdout.
        summary = WorkflowSummary(results=[])
        for source in sources:
            result = await workflow.process_one(source)
            summary.results.append(result)
            _print_per_file(result)
    finally:
        await vector.close()

    _print_summary(summary, originals_dir=originals_dir)
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
