"""Vector store service.

Async wrapper around Qdrant with BGE-M3 embeddings (via Ollama). Manages
two collections:

- `doc_chunks` — embeddings of OCR'd uploaded documents, filterable by
  `doc_id` so chat queries can be scoped to a specific document.
- `lex_uz` — embeddings of Uzbekistan customs-law text scraped from
  lex.uz. Populated once via `scripts/setup_rag.py`.

Both collections share the same embedding dimensionality and distance
metric. Search returns plain text payloads to keep the API simple — the
chat agent doesn't need full Qdrant point objects.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Final, Iterable, Sequence

from langchain_ollama import OllamaEmbeddings
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    Range,
    VectorParams,
)

from config.settings import OllamaSettings, QdrantSettings
from core.logging import get_logger

logger = get_logger(__name__)

_DISTANCE: Final[Distance] = Distance.COSINE
_BATCH_SIZE: Final[int] = 32  # texts per Ollama embedding call


@dataclass(frozen=True, slots=True)
class SearchHit:
    """A single semantic-search result."""

    text: str
    score: float
    metadata: dict[str, Any]


class VectorStoreService:
    """Async Qdrant + embeddings service."""

    _BATCH_SIZE: Final[int] = _BATCH_SIZE

    def __init__(
        self,
        qdrant_settings: QdrantSettings,
        ollama_settings: OllamaSettings,
    ) -> None:
        self._qs = qdrant_settings
        self._client = AsyncQdrantClient(
            host=qdrant_settings.host,
            port=qdrant_settings.port,
            prefer_grpc=False,
            check_compatibility=False,
        )
        embed_kwargs: dict = (
            {"headers": {"ngrok-skip-browser-warning": "true"}}
            if "ngrok" in ollama_settings.base_url
            else {}
        )
        self._embed = OllamaEmbeddings(
            base_url=ollama_settings.base_url,
            model=ollama_settings.embed_model,
            client_kwargs=embed_kwargs,
        )
        logger.info(
            "VectorStoreService ready (qdrant=%s, embed_model=%s)",
            qdrant_settings.url,
            ollama_settings.embed_model,
        )

    # ── Lifecycle ────────────────────────────────────────────────────

    async def close(self) -> None:
        await self._client.close()

    async def ensure_collections(self) -> None:
        """Create both collections if they don't already exist."""
        for name in (self._qs.doc_collection, self._qs.lex_collection):
            await self._ensure_collection(name)

    async def _ensure_collection(self, name: str) -> None:
        exists = await self._client.collection_exists(name)
        if exists:
            logger.debug("Collection %r already exists.", name)
            return
        await self._client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=self._qs.embedding_dim,
                distance=_DISTANCE,
            ),
        )
        logger.info("Created Qdrant collection %r (dim=%d).", name, self._qs.embedding_dim)

    # ── Upsert ───────────────────────────────────────────────────────

    async def upsert_doc_chunks(
        self, doc_id: str, chunks: Sequence[str]
    ) -> int:
        """Embed and store chunks of an uploaded document.

        Returns the number of points written.
        """
        if not chunks:
            return 0
        payloads = [{"doc_id": doc_id, "chunk_index": i, "text": c}
                    for i, c in enumerate(chunks)]
        return await self._upsert(self._qs.doc_collection, chunks, payloads)

    async def upsert_lex_chunks(
        self,
        chunks: Sequence[str],
        metadatas: Sequence[dict[str, Any]] | None = None,
    ) -> int:
        """Embed and store chunks of lex.uz customs law.

        `metadatas` must align with `chunks` if provided.
        """
        if not chunks:
            return 0
        if metadatas is None:
            metadatas = [{} for _ in chunks]
        if len(metadatas) != len(chunks):
            raise ValueError(
                f"metadatas length ({len(metadatas)}) does not match "
                f"chunks length ({len(chunks)})"
            )
        payloads = [{**m, "text": c} for c, m in zip(chunks, metadatas)]
        return await self._upsert(self._qs.lex_collection, chunks, payloads)

    async def _upsert(
        self,
        collection: str,
        texts: Sequence[str],
        payloads: Sequence[dict[str, Any]],
    ) -> int:
        """Embed and upsert in fixed-size batches.

        Single-shot embedding of thousands of texts overloads Ollama's
        embedding server (crashes with EOF on connection close). Batching
        keeps each call bounded and lets us recover/resume more cleanly.
        """
        if not texts:
            return 0

        total_batches = (len(texts) + self._BATCH_SIZE - 1) // self._BATCH_SIZE
        total_written = 0

        for batch_idx in range(total_batches):
            start = batch_idx * self._BATCH_SIZE
            end = start + self._BATCH_SIZE
            batch_texts = list(texts[start:end])
            batch_payloads = payloads[start:end]

            vectors = await self._embed.aembed_documents(batch_texts)
            points = [
                PointStruct(id=str(uuid.uuid4()), vector=vec, payload=payload)
                for vec, payload in zip(vectors, batch_payloads)
            ]
            await self._client.upsert(collection_name=collection, points=points)
            total_written += len(points)

            logger.info(
                "Upserted batch %d/%d into %r (%d / %d points)",
                batch_idx + 1, total_batches, collection,
                total_written, len(texts),
            )

        return total_written

    # ── Delete ───────────────────────────────────────────────────────

    async def delete_doc_chunks(self, doc_id: str) -> None:
        """Remove all Qdrant points for an uploaded document from doc_chunks."""
        await self._client.delete(
            collection_name=self._qs.doc_collection,
            points_selector=FilterSelector(
                filter=Filter(must=[
                    FieldCondition(key="doc_id", match=MatchValue(value=doc_id))
                ])
            ),
        )
        logger.info("Deleted doc_chunks for doc_id=%s", doc_id)

    async def delete_lex_source(self, source: str) -> None:
        """Remove all Qdrant points for a lex source (URL or filename)."""
        await self._client.delete(
            collection_name=self._qs.lex_collection,
            points_selector=FilterSelector(
                filter=Filter(must=[
                    FieldCondition(key="source", match=MatchValue(value=source))
                ])
            ),
        )
        logger.info("Deleted lex_uz chunks for source=%r", source)

    # ── Inventory ─────────────────────────────────────────────────────

    async def list_doc_chunk_counts(self) -> dict[str, int]:
        """Return {doc_id: chunk_count} for every doc in doc_chunks."""
        counts: dict[str, int] = {}
        offset = None
        while True:
            records, next_offset = await self._client.scroll(
                collection_name=self._qs.doc_collection,
                limit=500,
                offset=offset,
                with_payload=["doc_id"],
                with_vectors=False,
            )
            for rec in records:
                doc_id = (rec.payload or {}).get("doc_id", "")
                if doc_id:
                    counts[doc_id] = counts.get(doc_id, 0) + 1
            if next_offset is None:
                break
            offset = next_offset
        return counts

    async def list_lex_sources(self) -> list[dict[str, Any]]:
        """Return [{source, chunks}] for every unique source in lex_uz."""
        counts: dict[str, int] = {}
        offset = None
        while True:
            records, next_offset = await self._client.scroll(
                collection_name=self._qs.lex_collection,
                limit=500,
                offset=offset,
                with_payload=["source"],
                with_vectors=False,
            )
            for rec in records:
                src = (rec.payload or {}).get("source", "unknown")
                counts[src] = counts.get(src, 0) + 1
            if next_offset is None:
                break
            offset = next_offset
        return [
            {"source": s, "chunks": c}
            for s, c in sorted(counts.items(), key=lambda x: x[0])
        ]

    # ── Search ───────────────────────────────────────────────────────

    async def search_docs(
        self,
        query: str,
        doc_id: str | None = None,
        top_k: int = 5,
    ) -> list[SearchHit]:
        """Semantic search over uploaded-document chunks.

        Pass `doc_id` to restrict results to a single document.
        """
        query_filter = None
        if doc_id is not None:
            query_filter = Filter(must=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id))
            ])
        return await self._search(self._qs.doc_collection, query, top_k, query_filter)

    async def search_lex(self, query: str, top_k: int = 5) -> list[SearchHit]:
        """Semantic search over lex.uz customs-law chunks."""
        return await self._search(self._qs.lex_collection, query, top_k, query_filter=None)

    async def search_lex_with_context(
        self,
        query: str,
        top_k: int = 5,
        sibling_window: int = 1,
    ) -> list[SearchHit]:
        """Semantic search over lex.uz with sibling-chunk context expansion.

        After vector search finds the top-K seed hits, this method fetches
        adjacent chunks (same source + breadcrumb, chunk_index ± sibling_window)
        via a Qdrant scroll filter.  All unique chunks are sorted into document
        order before being returned, so the LLM always receives complete article
        text rather than an isolated middle fragment.
        """
        seed_hits = await self._search(
            self._qs.lex_collection, query, top_k, query_filter=None
        )
        if not seed_hits or sibling_window == 0:
            return seed_hits

        # keyed by (source, chunk_index) to deduplicate
        merged: dict[tuple, SearchHit] = {}

        for hit in seed_hits:
            source = hit.metadata.get("source", "")
            breadcrumb = hit.metadata.get("breadcrumb", "")
            chunk_index = hit.metadata.get("chunk_index")

            if chunk_index is None:
                merged[(source, id(hit))] = hit  # no index — keep as-is
                continue

            merged[(source, chunk_index)] = hit

            # Fetch siblings from Qdrant without re-embedding a query
            min_idx = max(0, chunk_index - sibling_window)
            max_idx = chunk_index + sibling_window

            filters = [
                FieldCondition(key="source", match=MatchValue(value=source)),
                FieldCondition(
                    key="chunk_index",
                    range=Range(gte=float(min_idx), lte=float(max_idx)),
                ),
            ]
            if breadcrumb:
                filters.append(
                    FieldCondition(key="breadcrumb", match=MatchValue(value=breadcrumb))
                )

            records, _ = await self._client.scroll(
                collection_name=self._qs.lex_collection,
                scroll_filter=Filter(must=filters),
                limit=sibling_window * 2 + 1,
                with_payload=True,
                with_vectors=False,
            )

            for rec in records:
                if not rec.payload:
                    continue
                idx = rec.payload.get("chunk_index", 0)
                key = (rec.payload.get("source", ""), idx)
                if key not in merged:
                    merged[key] = SearchHit(
                        text=str(rec.payload.get("text", "")),
                        # siblings inherit a slightly lower score
                        score=hit.score * 0.85,
                        metadata={
                            k: v for k, v in rec.payload.items() if k != "text"
                        },
                    )

        # Return in document order: sorted by (source, chunk_index)
        def _order(kv: tuple) -> tuple:
            (src, idx), _ = kv
            return (src, idx if isinstance(idx, (int, float)) else float("inf"))

        ordered = [hit for _, hit in sorted(merged.items(), key=_order)]
        logger.info(
            "search_lex_with_context: %d seed hits expanded to %d chunks",
            len(seed_hits), len(ordered),
        )
        return ordered

    async def _search(
        self,
        collection: str,
        query: str,
        top_k: int,
        query_filter: Filter | None,
    ) -> list[SearchHit]:
        if not query.strip():
            return []
        [query_vector] = await self._embed_texts([query])
        # qdrant-client >= 1.10 replaced `search()` with `query_points()`.
        # The response is a QueryResponse object — iterate `.points`.
        response = await self._client.query_points(
            collection_name=collection,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
        )
        return [
            SearchHit(
                text=str(hit.payload.get("text", "")) if hit.payload else "",
                score=float(hit.score),
                metadata={k: v for k, v in (hit.payload or {}).items() if k != "text"},
            )
            for hit in response.points
        ]

    # ── Embedding ────────────────────────────────────────────────────

    async def _embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        """Embed a batch of texts via Ollama."""
        return await self._embed.aembed_documents(list(texts))
