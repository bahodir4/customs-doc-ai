"""Ingest customs-law sources into the lex_uz Qdrant collection.

Accepts one or more sources — each can be a URL, a .docx file, or a
.md / .txt file. Each source is loaded, converted to markdown, chunked
hierarchically by `#`, `##`, `###` headers, and embedded into the
`lex_uz` collection.

Examples:
    # One URL
    python scripts/ingest_lex.py https://lex.uz/docs/3062271

    # Multiple URLs
    python scripts/ingest_lex.py \\
        https://lex.uz/docs/3062271 \\
        https://lex.uz/docs/some-resolution

    # Mix of URLs and local files
    python scripts/ingest_lex.py \\
        https://lex.uz/docs/3062271 \\
        docs/customs_code.docx \\
        notes/medical_devices.md
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from core.logging import configure_logging, get_logger
from core.services import VectorStoreService
from rag import HierarchicalChunker, IngestionResult, LexIngestionService
from rag.loaders import DocxLoader, MarkdownFileLoader, URLLoader

logger = get_logger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest customs-law sources into the lex_uz collection.",
    )
    parser.add_argument(
        "sources",
        nargs="+",
        help="One or more sources — URLs, .docx, .md, or .txt files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load + chunk only; print preview without embedding or uploading.",
    )
    parser.add_argument(
        "--preview-chunks",
        type=int,
        default=3,
        help="Number of chunks to preview in dry-run mode (default: 3)",
    )
    return parser.parse_args()


def _format_result(result: IngestionResult) -> str:
    return (
        f"  source       : {result.source}\n"
        f"  type         : {result.source_type}\n"
        f"  markdown     : {result.raw_markdown_chars:,} chars\n"
        f"  chunks       : {result.chunks_written}"
    )


async def _dry_run_one(src: str, preview_n: int) -> int:
    """Load + chunk only. Returns chunk count."""
    chunker = HierarchicalChunker(
        chunk_size=settings.rag.chunk_size,
        chunk_overlap=settings.rag.chunk_overlap,
    )

    src_str = str(src)
    if src_str.lower().startswith(("http://", "https://")):
        loader = URLLoader()
        markdown = await loader.load(src_str)
    else:
        path = Path(src_str)
        if not path.exists():
            raise FileNotFoundError(f"Not found: {path}")
        suffix = path.suffix.lower()
        if suffix == ".docx":
            markdown = await DocxLoader().load(str(path))
        elif suffix in {".md", ".markdown", ".txt"}:
            markdown = await MarkdownFileLoader().load(str(path))
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

    chunks = chunker.chunk(markdown, source=src_str)

    # Counts by heading depth
    h1 = sum(1 for c in chunks if c.headers.get("h1"))
    h2 = sum(1 for c in chunks if c.headers.get("h2"))
    h3 = sum(1 for c in chunks if c.headers.get("h3"))

    print(f"  markdown : {len(markdown):,} chars")
    print(f"  chunks   : {len(chunks)}")
    print(f"  with h1  : {h1}")
    print(f"  with h2  : {h2}")
    print(f"  with h3  : {h3}")
    print()
    print(f"  --- first {preview_n} chunk(s) preview ---")
    for c in chunks[:preview_n]:
        print()
        print(f"  [chunk {c.chunk_index}] breadcrumb: {c.to_metadata()['breadcrumb'] or '(none)'}")
        body = c.text[:300].replace("\n", "\n    ")
        print(f"    {body}{'...' if len(c.text) > 300 else ''}")
    return len(chunks)


async def main() -> int:
    args = _parse_args()
    configure_logging(settings.log_level)

    # Dry-run mode: just load + chunk, no embedding.
    if args.dry_run:
        total = 0
        for src in args.sources:
            print(f"\n→ Dry-run: {src}")
            try:
                total += await _dry_run_one(src, args.preview_chunks)
            except Exception as exc:
                logger.exception("Dry-run failed for %s", src)
                print(f"  FAILED: {exc}")
        print()
        print("─" * 60)
        print(f"Total chunks that WOULD be ingested: {total}")
        return 0

    # Real ingestion path
    vector = VectorStoreService(settings.qdrant, settings.ollama)
    service = LexIngestionService(vector_store=vector)

    total_written = 0
    failures: list[tuple[str, str]] = []

    try:
        for src in args.sources:
            print(f"\n→ Ingesting: {src}")
            try:
                result = await service.ingest(src)
                print(_format_result(result))
                total_written += result.chunks_written
            except Exception as exc:
                logger.exception("Failed to ingest %s", src)
                failures.append((src, str(exc)))
                print(f"  FAILED: {exc}")
    finally:
        await vector.close()

    print()
    print("─" * 60)
    print(f"Total chunks ingested: {total_written}")
    if failures:
        print(f"Failures: {len(failures)}")
        for src, err in failures:
            print(f"  - {src}: {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
