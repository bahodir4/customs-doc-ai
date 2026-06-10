"""Smoke tests for VectorStoreService."""
from __future__ import annotations

import pytest

from core.services import SearchHit, VectorStoreService


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ensure_collections_is_idempotent(
    vector_store: VectorStoreService,
) -> None:
    await vector_store.ensure_collections()
    await vector_store.ensure_collections()  # second call must not error


@pytest.mark.asyncio
@pytest.mark.integration
async def test_doc_chunks_upsert_and_search(
    vector_store: VectorStoreService,
) -> None:
    await vector_store.ensure_collections()

    doc_id = "smoke-test-doc-001"
    chunks = [
        "Invoice number HQPL00073841 issued by Ascensia Diabetes Care AG, Basel.",
        "Total amount: 212,584.80 EUR. Currency: EUR. Incoterms: DAP Tashkent.",
        "Buyer: FE Medical Online Services LLC, Tashkent, Uzbekistan.",
    ]
    written = await vector_store.upsert_doc_chunks(doc_id, chunks)
    assert written == len(chunks)

    hits = await vector_store.search_docs(
        query="Who is the seller of the invoice?",
        doc_id=doc_id,
        top_k=3,
    )
    assert hits, "expected at least one search hit"
    assert all(isinstance(h, SearchHit) for h in hits)
    assert all(h.metadata.get("doc_id") == doc_id for h in hits)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_doc_filter_isolates_results(
    vector_store: VectorStoreService,
) -> None:
    await vector_store.ensure_collections()
    await vector_store.upsert_doc_chunks("doc-a", ["alpha content one"])
    await vector_store.upsert_doc_chunks("doc-b", ["bravo content two"])

    hits = await vector_store.search_docs(query="content", doc_id="doc-a", top_k=5)
    assert all(h.metadata.get("doc_id") == "doc-a" for h in hits)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_empty_chunks_returns_zero(vector_store: VectorStoreService) -> None:
    await vector_store.ensure_collections()
    assert await vector_store.upsert_doc_chunks("doc-empty", []) == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_lex_metadata_mismatch_raises(
    vector_store: VectorStoreService,
) -> None:
    with pytest.raises(ValueError, match="length"):
        await vector_store.upsert_lex_chunks(
            chunks=["a", "b"],
            metadatas=[{"source": "lex.uz"}],  # off by one
        )
