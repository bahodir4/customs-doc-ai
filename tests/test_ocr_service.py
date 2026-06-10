"""Smoke tests for OCRService."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.services import ExtractionResult, OCRService


def test_unsupported_extension_rejected(ocr_service: OCRService, tmp_path: Path) -> None:
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    with pytest.raises(ValueError, match="Unsupported file type"):
        # Schedule the coroutine in a tight loop so the sync test sees the error.
        import asyncio
        asyncio.run(ocr_service.extract_text(bad))


def test_missing_file_raises(ocr_service: OCRService, tmp_path: Path) -> None:
    missing = tmp_path / "ghost.pdf"
    import asyncio
    with pytest.raises(FileNotFoundError):
        asyncio.run(ocr_service.extract_text(missing))


@pytest.mark.asyncio
@pytest.mark.integration
async def test_extract_from_sample_pdf(
    ocr_service: OCRService, sample_pdf_path: Path
) -> None:
    result = await ocr_service.extract_text(sample_pdf_path)
    assert isinstance(result, ExtractionResult)
    assert result.source_path == sample_pdf_path
    assert result.page_count >= 1
    assert result.text.strip(), "OCR returned empty text"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_extract_from_sample_image(
    ocr_service: OCRService, sample_image_path: Path
) -> None:
    result = await ocr_service.extract_text(sample_image_path)
    assert result.ocr_used is True
    assert result.page_count == 1
    assert result.text.strip()
