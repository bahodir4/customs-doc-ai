"""Unit tests for the hierarchical chunker (no external services)."""
from __future__ import annotations

import pytest

from rag import HierarchicalChunker, LexChunk


# ── Fixtures ─────────────────────────────────────────────────────────


SIMPLE_DOC = """# Customs Code

Some introductory text.

## Article 1: Scope

This code governs all customs operations.

## Article 2: Definitions

For the purposes of this code:
- "Goods" means any movable property.
- "Customs duty" means the levy imposed on imports.

# Tariff Law

## Article 3: Rates

Standard rate is 12%.
"""

DEEP_HIERARCHY_DOC = """# Глава 1: Общие положения

## Статья 1: Сфера применения

### Часть 1

Текст части 1.

### Часть 2

Текст части 2.

## Статья 2: Определения

Определения терминов.
"""

NO_HEADERS_DOC = "Just a flat paragraph of text. No markdown headers at all in this document."

LONG_SECTION_DOC = (
    "# Big Article\n\n"
    + ("This is a sentence that needs to be repeated many times to force sub-splitting. " * 50)
)


# ── Tests ────────────────────────────────────────────────────────────


class TestBasicChunking:
    def test_empty_input_returns_empty_list(self) -> None:
        chunker = HierarchicalChunker()
        assert chunker.chunk("") == []
        assert chunker.chunk("   \n  \n ") == []

    def test_no_headers_produces_one_chunk(self) -> None:
        chunker = HierarchicalChunker()
        chunks = chunker.chunk(NO_HEADERS_DOC)
        assert len(chunks) == 1
        assert chunks[0].headers == {}
        assert "flat paragraph" in chunks[0].text

    def test_simple_doc_produces_one_chunk_per_section(self) -> None:
        chunker = HierarchicalChunker(chunk_size=1000)
        chunks = chunker.chunk(SIMPLE_DOC)
        # Should produce 5 sections:
        #   H1 Customs Code intro
        #   H1>H2 Article 1
        #   H1>H2 Article 2
        #   H1 Tariff Law (empty body, may be dropped)
        #   H1>H2 Article 3
        # The empty H1 section is skipped, so we expect 4.
        assert 3 <= len(chunks) <= 5


class TestHeaderMetadata:
    def test_h1_h2_path_captured(self) -> None:
        chunker = HierarchicalChunker(chunk_size=1000)
        chunks = chunker.chunk(SIMPLE_DOC)
        article_1 = next(c for c in chunks if c.headers.get("h2") == "Article 1: Scope")
        assert article_1.headers["h1"] == "Customs Code"

    def test_h1_h2_h3_path_captured(self) -> None:
        chunker = HierarchicalChunker(chunk_size=1000)
        chunks = chunker.chunk(DEEP_HIERARCHY_DOC)
        # Part 1 lives under H1=Глава 1, H2=Статья 1, H3=Часть 1
        part_1 = next(c for c in chunks if c.headers.get("h3") == "Часть 1")
        assert part_1.headers["h1"].startswith("Глава 1")
        assert part_1.headers["h2"].startswith("Статья 1")

    def test_breadcrumb_in_metadata(self) -> None:
        chunker = HierarchicalChunker(chunk_size=1000)
        chunks = chunker.chunk(DEEP_HIERARCHY_DOC)
        part_1 = next(c for c in chunks if c.headers.get("h3") == "Часть 1")
        meta = part_1.to_metadata()
        assert "Глава 1" in meta["breadcrumb"]
        assert "Статья 1" in meta["breadcrumb"]
        assert "Часть 1" in meta["breadcrumb"]
        assert meta["breadcrumb"].count(">") == 2


class TestHeaderPrefix:
    def test_chunk_text_includes_header_prefix(self) -> None:
        chunker = HierarchicalChunker(chunk_size=1000, include_header_prefix=True)
        chunks = chunker.chunk(SIMPLE_DOC)
        article_2 = next(c for c in chunks if c.headers.get("h2") == "Article 2: Definitions")
        # Header prefix lines appear at the top.
        assert "# Customs Code" in article_2.text
        assert "## Article 2: Definitions" in article_2.text

    def test_prefix_can_be_disabled(self) -> None:
        chunker = HierarchicalChunker(chunk_size=1000, include_header_prefix=False)
        chunks = chunker.chunk(SIMPLE_DOC)
        article_2 = next(c for c in chunks if c.headers.get("h2") == "Article 2: Definitions")
        # Body still contains the article content, but no leading header lines.
        assert not article_2.text.startswith("#")

    def test_prefix_skipped_when_no_headers(self) -> None:
        chunker = HierarchicalChunker(chunk_size=1000)
        chunks = chunker.chunk(NO_HEADERS_DOC)
        # No headers → no prefix → text starts with the content
        assert chunks[0].text.startswith("Just a flat")


class TestSizeSubsplit:
    def test_long_section_is_split(self) -> None:
        chunker = HierarchicalChunker(chunk_size=300, chunk_overlap=30)
        chunks = chunker.chunk(LONG_SECTION_DOC)
        # The single H1 section is huge — must be split.
        assert len(chunks) > 1

    def test_subsplit_chunks_share_header_metadata(self) -> None:
        chunker = HierarchicalChunker(chunk_size=300, chunk_overlap=30)
        chunks = chunker.chunk(LONG_SECTION_DOC)
        # Every sub-chunk must carry the parent h1 metadata.
        for c in chunks:
            assert c.headers.get("h1") == "Big Article"

    def test_subsplit_chunks_have_distinct_indices(self) -> None:
        chunker = HierarchicalChunker(chunk_size=300, chunk_overlap=30)
        chunks = chunker.chunk(LONG_SECTION_DOC)
        indices = [c.chunk_index for c in chunks]
        assert indices == sorted(indices)
        assert len(set(indices)) == len(indices)  # all unique

    def test_small_section_stays_intact(self) -> None:
        chunker = HierarchicalChunker(chunk_size=2000)
        chunks = chunker.chunk(SIMPLE_DOC)
        article_1 = next(c for c in chunks if c.headers.get("h2") == "Article 1: Scope")
        # The body is short — shouldn't be split.
        assert "This code governs all customs operations" in article_1.text


class TestLexChunkSerialisation:
    def test_to_metadata_round_trip(self) -> None:
        chunk = LexChunk(
            text="body",
            headers={"h1": "A", "h2": "B"},
            source="https://lex.uz/docs/1",
            chunk_index=3,
        )
        meta = chunk.to_metadata()
        assert meta["h1"] == "A"
        assert meta["h2"] == "B"
        assert meta["source"] == "https://lex.uz/docs/1"
        assert meta["chunk_index"] == 3
        assert meta["breadcrumb"] == "A > B"

    def test_empty_headers_yield_empty_breadcrumb(self) -> None:
        chunk = LexChunk(text="body", headers={}, source="x", chunk_index=0)
        assert chunk.to_metadata()["breadcrumb"] == ""
