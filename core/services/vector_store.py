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
    MatchValue,
    PointStruct,
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
        self._embed = OllamaEmbeddings(
            base_url=ollama_settings.base_url,
            model=ollama_settings.embed_model,
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
