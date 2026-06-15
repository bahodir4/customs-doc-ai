"""Smart hierarchical chunker for legal / structured documents.

The strategy is two-stage:

1. **Header split** — `MarkdownHeaderTextSplitter` carves the document at
   `#`, `##`, `###` boundaries. Each piece comes with metadata
   `{h1, h2, h3}` describing its position in the hierarchy.

2. **Size split** — any piece whose body exceeds the target chunk size
   is further sub-split by `RecursiveCharacterTextSplitter`, preserving
   the parent headers in each sub-chunk.

For every emitted chunk, we **prefix the header path into the chunk text
itself**. This is the key trick: the embedding now carries section
context, so a query like "what does Article 5 say about medical devices?"
matches a chunk whose body would otherwise just read
"...subject to customs duty...".

The same metadata is also attached to the chunk for filtering, UI
display, and source attribution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from core.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_HEADERS: Final[list[tuple[str, str]]] = [
    ("#", "h1"),
    ("##", "h2"),
    # ### is intentionally omitted — sub-sections stay inside their parent ##
    # chunk so the LLM always receives a complete article when retrieved.
]

# A header section under this length is kept as one chunk even if it's
# slightly larger than chunk_size — splitting tiny articles would lose
# semantic coherence.
_KEEP_INTACT_RATIO: Final[float] = 1.5


@dataclass(frozen=True, slots=True)
class LexChunk:
    """A single chunk ready to upsert into the lex_uz Qdrant collection."""

    text: str                          # body, with header prefix prepended
    headers: dict[str, str] = field(default_factory=dict)
    source: str = ""
    chunk_index: int = 0

    def to_metadata(self) -> dict[str, Any]:
        """Build the Qdrant payload for this chunk."""
        breadcrumb = " > ".join(
            v for v in (
                self.headers.get("h1"),
                self.headers.get("h2"),
                self.headers.get("h3"),
            ) if v
        )
        return {
            **self.headers,
            "source": self.source,
            "chunk_index": self.chunk_index,
            "breadcrumb": breadcrumb,
        }


class HierarchicalChunker:
    """Two-stage chunker: header-aware first, then size-aware."""

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        headers_to_split_on: list[tuple[str, str]] | None = None,
        include_header_prefix: bool = True,
    ) -> None:
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._headers = headers_to_split_on or _DEFAULT_HEADERS
        self._include_prefix = include_header_prefix

        # strip_headers=False keeps the # lines as plain text inside each
        # section so we can re-include them ourselves; otherwise the
        # MarkdownHeaderTextSplitter eats the heading line entirely.
        self._md_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self._headers,
            strip_headers=True,
        )
        self._char_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def chunk(self, markdown: str, source: str = "") -> list[LexChunk]:
        """Chunk a markdown document. Returns ordered LexChunk list."""
        if not markdown or not markdown.strip():
            return []

        # Stage 1: split by markdown headers.
        header_chunks = self._md_splitter.split_text(markdown)
        logger.debug("Header split produced %d sections", len(header_chunks))

        # Stage 2: ensure no chunk is too big.
        final: list[LexChunk] = []
        index = 0
        max_size = int(self._chunk_size * _KEEP_INTACT_RATIO)

        for section in header_chunks:
            body = section.page_content.strip()
            if not body:
                continue
            section_meta = dict(section.metadata or {})

            if len(body) <= max_size:
                final.append(self._make_chunk(body, section_meta, source, index))
                index += 1
            else:
                # Split the section further while keeping its headers.
                sub_parts = self._char_splitter.split_text(body)
                for sub in sub_parts:
                    if not sub.strip():
                        continue
                    final.append(self._make_chunk(sub, section_meta, source, index))
                    index += 1

        logger.info(
            "Chunked into %d pieces (header_sections=%d, source=%s)",
            len(final), len(header_chunks), source or "<inline>",
        )
        return final

    def _make_chunk(
        self,
        body: str,
        headers: dict[str, str],
        source: str,
        index: int,
    ) -> LexChunk:
        text = self._prefix_body_with_headers(body, headers) if self._include_prefix else body
        return LexChunk(
            text=text,
            headers=headers,
            source=source,
            chunk_index=index,
        )

    @staticmethod
    def _prefix_body_with_headers(body: str, headers: dict[str, str]) -> str:
        """Prepend the hierarchical header path so embeddings see it."""
        prefix_lines: list[str] = []
        if headers.get("h1"):
            prefix_lines.append(f"# {headers['h1']}")
        if headers.get("h2"):
            prefix_lines.append(f"## {headers['h2']}")
        if headers.get("h3"):
            prefix_lines.append(f"### {headers['h3']}")
        if not prefix_lines:
            return body
        return "\n".join(prefix_lines) + "\n\n" + body
