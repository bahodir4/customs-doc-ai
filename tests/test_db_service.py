"""Smoke tests for DBService."""
from __future__ import annotations

import pytest

from core.services import DBService

SAMPLE_INVOICE = {
    "doc_type": "invoice",
    "file_name": "HQPL00073841.pdf",
    "file_path": "/tmp/HQPL00073841.pdf",
    "raw_text": "Invoice HQPL00073841 from Ascensia to FE Medical Online Services...",
    "extracted_data": {
        "invoice_number": "HQPL00073841",
        "total_amount": 212584.80,
        "currency": "EUR",
    },
}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_save_and_get_roundtrip(db_service: DBService) -> None:
    doc_id = await db_service.save_document(**SAMPLE_INVOICE)
    fetched = await db_service.get_document(doc_id)

    assert fetched is not None
    assert fetched["id"] == doc_id
    assert fetched["doc_type"] == "invoice"
    assert fetched["extracted_data"]["invoice_number"] == "HQPL00073841"
    assert fetched["validation_errors"] == []
    assert fetched["status"] == "done"

    await db_service.delete_document(doc_id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_documents_filter_by_type(db_service: DBService) -> None:
    invoice_id = await db_service.save_document(**SAMPLE_INVOICE)
    awb_id = await db_service.save_document(
        doc_type="awb",
        file_name="awb.jpg",
        file_path="/tmp/awb.jpg",
        raw_text="AWB 488-40007166",
        extracted_data={"awb_number": "488-40007166"},
    )
    try:
        invoices = await db_service.list_documents(doc_type="invoice")
        assert any(d["id"] == invoice_id for d in invoices)
        assert all(d["doc_type"] == "invoice" for d in invoices)

        awbs = await db_service.list_documents(doc_type="awb")
        assert any(d["id"] == awb_id for d in awbs)
    finally:
        await db_service.delete_document(invoice_id)
        await db_service.delete_document(awb_id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_extraction(db_service: DBService) -> None:
    doc_id = await db_service.save_document(**SAMPLE_INVOICE)
    try:
        corrected = {**SAMPLE_INVOICE["extracted_data"], "total_amount": 212585.00}
        ok = await db_service.update_extraction(
            doc_id, extracted_data=corrected, validation_errors=["rounded total"]
        )
        assert ok

        fetched = await db_service.get_document(doc_id)
        assert fetched["extracted_data"]["total_amount"] == 212585.00
        assert fetched["validation_errors"] == ["rounded total"]
    finally:
        await db_service.delete_document(doc_id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_missing_returns_none(db_service: DBService) -> None:
    assert await db_service.get_document("00000000-0000-0000-0000-000000000000") is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_documents_batch(db_service: DBService) -> None:
    ids = [
        await db_service.save_document(**SAMPLE_INVOICE),
        await db_service.save_document(**SAMPLE_INVOICE),
    ]
    try:
        results = await db_service.get_documents(ids)
        assert len(results) == 2
        assert {r["id"] for r in results} == set(ids)
    finally:
        for doc_id in ids:
            await db_service.delete_document(doc_id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_invalid_status_raises(db_service: DBService) -> None:
    with pytest.raises(ValueError, match="Invalid status"):
        await db_service.save_document(**SAMPLE_INVOICE, status="banana")
