"""Tests for the chat agent graph."""
from __future__ import annotations

import pytest
import pytest_asyncio

from core.pipeline import build_chat_agent
from core.pipeline.chat_agent import _build_context, _identify_sources


# ── Pure unit tests (no services) ────────────────────────────────────


class TestContextBuilder:
    def test_empty_state_returns_placeholder(self) -> None:
        assert _build_context({}) == "(no context retrieved)"

    def test_lex_only(self) -> None:
        ctx = _build_context({"lex_chunks": ["Article 1: ..."]})
        assert "customs-law" in ctx
        assert "Article 1" in ctx

    def test_doc_only(self) -> None:
        ctx = _build_context({"doc_chunks": ["Invoice excerpt"]})
        assert "document excerpts" in ctx
        assert "Invoice excerpt" in ctx

    def test_pg_only(self) -> None:
        ctx = _build_context({
            "pg_documents": [
                {"id": "abc", "doc_type": "invoice", "extracted_data": {"x": 1}}
            ]
        })
        assert "Structured document fields" in ctx
        assert "abc" in ctx
        assert '"x": 1' in ctx

    def test_all_three_sources(self) -> None:
        ctx = _build_context({
            "pg_documents": [{"id": "a", "doc_type": "invoice", "extracted_data": {}}],
            "doc_chunks": ["chunk-1"],
            "lex_chunks": ["lex-1"],
        })
        assert "Structured document fields" in ctx
        assert "document excerpts" in ctx
        assert "customs-law" in ctx


class TestIdentifySources:
    def test_empty_state(self) -> None:
        assert _identify_sources({}) == []

    def test_doc_qa_sources(self) -> None:
        result = _identify_sources({
            "pg_documents": [{"id": "a"}],
            "doc_chunks": ["x"],
        })
        assert "postgresql" in result
        assert "doc_chunks" in result
        assert "lex_uz" not in result

    def test_rag_sources(self) -> None:
        result = _identify_sources({"lex_chunks": ["x"]})
        assert result == ["lex_uz"]

    def test_hybrid_sources(self) -> None:
        result = _identify_sources({
            "pg_documents": [{"id": "a"}],
            "doc_chunks": ["x"],
            "lex_chunks": ["y"],
        })
        assert set(result) == {"postgresql", "doc_chunks", "lex_uz"}


# ── Integration tests (require live services) ────────────────────────


@pytest_asyncio.fixture
async def chat_agent_compiled(llm_service, vector_store, db_service):
    return build_chat_agent(llm_service, vector_store, db_service)


@pytest_asyncio.fixture
async def seeded_chunks(vector_store):
    """Pre-populate both Qdrant collections with deterministic test content."""
    await vector_store.ensure_collections()

    # doc_chunks
    await vector_store.upsert_doc_chunks(
        "chat-test-doc-001",
        [
            "Invoice number HQPL00073841 issued by Ascensia Diabetes Care AG.",
            "Total amount: 212584.80 EUR. Currency: EUR. Incoterms: DAP Tashkent.",
        ],
    )

    # lex_uz
    await vector_store.upsert_lex_chunks(
        chunks=[
            "Article 1. Customs duties on medical diagnostic devices in Uzbekistan are zero-rated when accompanied by registration certificates per Cabinet Resolution No. 408.",
            "Article 2. HS code 3822 covers diagnostic and laboratory reagents.",
        ],
        metadatas=[
            {"source": "test", "article": "1"},
            {"source": "test", "article": "2"},
        ],
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_chat_returns_response_with_sources(
    chat_agent_compiled, seeded_chunks
) -> None:
    """The agent should detect language, route, retrieve, and respond."""
    result = await chat_agent_compiled.ainvoke({
        "user_input": "What is the customs duty for medical diagnostic devices in Uzbekistan?",
        "context_doc_ids": [],
    })

    assert result.get("final_response"), "no response returned"
    assert result.get("detected_language") in {"uz", "ru", "en"}
    assert result.get("intent") in {"doc_qa", "rag", "hybrid"}
    assert result.get("sources_used"), "no sources reported"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_chat_with_doc_ids_includes_pg_source(
    chat_agent_compiled, seeded_chunks, db_service
) -> None:
    """When context_doc_ids is set, the structured fields source should fire."""
    doc_id = await db_service.save_document(
        doc_type="invoice",
        file_name="test.pdf",
        file_path="/tmp/test.pdf",
        raw_text="HQPL00073841 Ascensia 212584.80 EUR",
        extracted_data={
            "invoice_number": "HQPL00073841",
            "total_amount": 212584.80,
            "currency": "EUR",
        },
    )
    try:
        result = await chat_agent_compiled.ainvoke({
            "user_input": "What is the total amount of the invoice?",
            "context_doc_ids": [doc_id],
        })
        assert result.get("final_response")
        # When doc_ids are provided AND intent isn't pure rag, pg should be there.
        if result.get("intent") in {"doc_qa", "hybrid"}:
            assert "postgresql" in result.get("sources_used", [])
    finally:
        await db_service.delete_document(doc_id)
