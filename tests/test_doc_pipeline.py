"""Tests for the document-processing pipeline.

Unit tests verify graph construction and the pure helper logic without
hitting any external service. Integration tests use a synthetic PDF
(built on the fly with PyMuPDF) so they don't require sample files.
"""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
import pytest
import pytest_asyncio

from core.pipeline import build_doc_pipeline
from core.pipeline.doc_pipeline import _build_chunker, _is_error


# ── Pure unit tests (no services) ────────────────────────────────────


class TestPipelineHelpers:
    def test_is_error_detects_error_status(self) -> None:
        assert _is_error({"status": "error"}) is True
        assert _is_error({"status": "processing"}) is False
        assert _is_error({"status": "done"}) is False
        assert _is_error({}) is False

    def test_chunker_splits_long_text(self) -> None:
        chunker = _build_chunker()
        text = ("Invoice line " * 200).strip()
        chunks = chunker.split_text(text)
        assert len(chunks) > 1
        assert all(c.strip() for c in chunks)

    def test_chunker_keeps_short_text_intact(self) -> None:
        chunker = _build_chunker()
        chunks = chunker.split_text("Short invoice text.")
        assert len(chunks) == 1


# ── Integration tests (require live services) ────────────────────────


@pytest.fixture
def synthetic_invoice_pdf(tmp_path: Path) -> Path:
    """Generate a real PDF with an invoice-like text layer."""
    pdf_path = tmp_path / "test_invoice.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (50, 50),
        (
            "COMMERCIAL INVOICE\n\n"
            "Invoice Number: TEST-INV-001\n"
            "Date: 2025-01-15\n\n"
            "Seller: Test Suppliers AG\n"
            "Bahnhofstrasse 1, 8001 Zurich, Switzerland\n"
            "VAT: CHE-123.456.789\n\n"
            "Buyer: Test Buyer LLC\n"
            "Tashkent, Uzbekistan\n\n"
            "Item   Description    HS Code     Qty   Price    Amount\n"
            "1      Widgets        8473300000  100   1.00     100.00\n\n"
            "Total: 100.00 EUR\n"
            "Currency: EUR\n"
            "Incoterms: DAP Tashkent\n"
        ),
        fontsize=10,
    )
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest_asyncio.fixture
async def doc_pipeline_compiled(
    ocr_service, llm_service, vector_store, db_service
):
    return build_doc_pipeline(ocr_service, llm_service, vector_store, db_service)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_pipeline_processes_synthetic_invoice(
    doc_pipeline_compiled, synthetic_invoice_pdf: Path
) -> None:
    """Full end-to-end: PDF → OCR → classify → extract → validate → store."""
    result = await doc_pipeline_compiled.ainvoke(
        {"file_path": str(synthetic_invoice_pdf)}
    )

    assert result["status"] == "done", f"failed: {result.get('error_message')}"
    assert result["doc_id"], "no doc_id returned"
    assert result["doc_type"] == "invoice"
    assert result["ocr_used"] is False, "synthetic PDF has text layer; OCR shouldn't run"
    assert result["raw_text"], "raw_text should be populated"

    # Spot-check the mandatory field made it through extraction + validation.
    extracted = result["extracted_data"]
    assert extracted.get("invoice_number") == "TEST-INV-001"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_pipeline_handles_missing_file(doc_pipeline_compiled) -> None:
    """Missing file produces an error record, but the pipeline still completes."""
    result = await doc_pipeline_compiled.ainvoke(
        {"file_path": "/nonexistent/ghost.pdf"}
    )
    assert result["status"] == "error"
    assert "not found" in (result.get("error_message") or "").lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_pipeline_persists_via_doc_id(
    doc_pipeline_compiled, synthetic_invoice_pdf: Path, db_service
) -> None:
    """The returned doc_id must be retrievable from the database."""
    result = await doc_pipeline_compiled.ainvoke(
        {"file_path": str(synthetic_invoice_pdf)}
    )
    assert result["status"] == "done"

    saved = await db_service.get_document(result["doc_id"])
    assert saved is not None
    assert saved["doc_type"] == "invoice"
    assert saved["extracted_data"].get("invoice_number") == "TEST-INV-001"

    # Cleanup
    await db_service.delete_document(result["doc_id"])
