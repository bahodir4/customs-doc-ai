"""OCR service.

Extracts text from PDFs and images using per-page smart routing:

- For each PDF page independently: if the embedded text layer has ≥ 50 chars
  the page is digital-born → use text layer (fast, accurate).
  If not → render the page at 300 DPI and run PaddleOCR (scanned fallback).
- Image files (jpg/png) go straight to PaddleOCR.

PaddleOCR results are sorted into reading order (top-to-bottom, left-to-right)
and low-confidence detections (< 0.5) are discarded.

PaddleOCR is initialised lazily on first use because model loading is slow
(~5 s) and we don't want that hit on import.
"""
from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import fitz  # PyMuPDF
from PIL import Image

from core.logging import get_logger

logger = get_logger(__name__)

_SUPPORTED_IMAGE_EXT: Final[frozenset[str]] = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"})
_PDF_EXT: Final[str] = ".pdf"
_MIN_TEXT_CHARS_PER_PAGE: Final[int] = 150  # fewer chars → assume scanned/partial-image page
_OCR_RENDER_DPI: Final[int] = 300           # higher DPI → better accuracy on dense docs
_OCR_MIN_CONFIDENCE: Final[float] = 0.35   # lower threshold keeps small text in dense forms
_OCR_LINE_BAND_PX: Final[int] = 15          # vertical band size for reading-order grouping


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Outcome of a single OCR run."""

    text: str
    page_count: int
    ocr_used: bool          # True if any page went through PaddleOCR
    source_path: Path
    text_layer_pages: int = 0   # pages served from embedded text layer
    ocr_pages: int = 0          # pages that required PaddleOCR


class OCRService:
    """Extracts text from PDF and image files.

    The PaddleOCR engine is created on first call. Pass `language` to control
    the recognition model — 'en' handles Latin scripts (English, Uzbek Latin),
    'cyrillic' handles Russian. Default 'en' is the safest mixed-content
    choice for Uzbek customs documents which are predominantly Latin.
    """

    def __init__(self, language: str = "en") -> None:
        self._language = language
        self._engine = None  # PaddleOCR — lazy

    @property
    def language(self) -> str:
        return self._language

    def _get_engine(self):  # noqa: ANN202 — PaddleOCR has no public type
        """Lazy-load PaddleOCR. First call takes a few seconds."""
        if self._engine is None:
            logger.info("Initialising PaddleOCR (lang=%s)...", self._language)
            from paddleocr import PaddleOCR

            self._engine = PaddleOCR(
                use_angle_cls=True,
                lang=self._language,
                show_log=False,
                use_gpu=False,
            )
            logger.info("PaddleOCR ready.")
        return self._engine

    async def extract_text(self, file_path: str | Path) -> ExtractionResult:
        """Public entry point. Routes by file extension."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File does not exist: {path}")

        suffix = path.suffix.lower()
        if suffix == _PDF_EXT:
            return await self._extract_pdf(path)
        if suffix in _SUPPORTED_IMAGE_EXT:
            return await self._extract_image(path)
        raise ValueError(
            f"Unsupported file type: {suffix!r}. "
            f"Supported: {_PDF_EXT}, {', '.join(sorted(_SUPPORTED_IMAGE_EXT))}"
        )

    async def _extract_pdf(self, path: Path) -> ExtractionResult:
        """Per-page smart routing: text layer for digital pages, OCR for scanned ones."""
        return await asyncio.to_thread(self._extract_pdf_smart, path)

    async def _extract_image(self, path: Path) -> ExtractionResult:
        """OCR a single image file."""
        text = await asyncio.to_thread(self._ocr_image_file, path)
        return ExtractionResult(
            text=text,
            page_count=1,
            ocr_used=True,
            source_path=path,
            text_layer_pages=0,
            ocr_pages=1,
        )

    def _extract_pdf_smart(self, path: Path) -> ExtractionResult:
        """Synchronous per-page extraction with intelligent text-layer vs OCR routing.

        Each page is assessed independently:
        - Digital page (≥ _MIN_TEXT_CHARS_PER_PAGE chars in text layer) → text layer.
        - Scanned page → render at _OCR_RENDER_DPI and run PaddleOCR.

        Mixed documents (some digital, some scanned) are handled correctly because
        routing happens at page granularity, not document granularity.
        """
        parts: list[str] = []
        text_layer_pages = 0
        ocr_pages = 0
        engine = None

        with fitz.open(path) as doc:
            page_count = doc.page_count
            for page_idx, page in enumerate(doc, start=1):
                page_text = page.get_text().strip()

                if len(page_text) >= _MIN_TEXT_CHARS_PER_PAGE:
                    text_layer_pages += 1
                    parts.append(f"--- Page {page_idx} ---\n{page_text}")
                    logger.debug("Page %d/%d: text layer (%d chars)", page_idx, page_count, len(page_text))
                else:
                    if engine is None:
                        engine = self._get_engine()
                    pix = page.get_pixmap(dpi=_OCR_RENDER_DPI)
                    image_bytes = pix.tobytes("png")
                    ocr_text = self._ocr_image_bytes(engine, image_bytes)
                    ocr_pages += 1
                    label = f"--- Page {page_idx} [OCR] ---"
                    parts.append(f"{label}\n{ocr_text}" if ocr_text else f"{label}\n(no text detected)")
                    logger.debug("Page %d/%d: OCR (%d chars)", page_idx, page_count, len(ocr_text))

        logger.info(
            "PDF %r: %d pages total — %d text-layer, %d OCR",
            path.name, page_count, text_layer_pages, ocr_pages,
        )
        return ExtractionResult(
            text="\n\n".join(parts),
            page_count=page_count,
            ocr_used=ocr_pages > 0,
            source_path=path,
            text_layer_pages=text_layer_pages,
            ocr_pages=ocr_pages,
        )

    def _ocr_image_file(self, path: Path) -> str:
        """OCR a single image from disk."""
        engine = self._get_engine()
        return self._ocr_image_bytes(engine, path.read_bytes())

    @staticmethod
    def _ocr_image_bytes(engine, image_bytes: bytes) -> str:  # noqa: ANN001
        """Run PaddleOCR on raw image bytes; return text sorted into reading order."""
        import numpy as np

        with Image.open(io.BytesIO(image_bytes)) as img:
            img_rgb = img.convert("RGB")
            arr = np.array(img_rgb)

        result = engine.ocr(arr, cls=True)
        if not result or not result[0]:
            return ""

        entries = result[0]

        def _reading_order_key(entry):
            bbox = entry[0]  # [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]
            y_top = min(pt[1] for pt in bbox)
            x_left = min(pt[0] for pt in bbox)
            # Bucket vertically into ~15px bands so items on the same line
            # sort left-to-right rather than by exact floating-point Y.
            return (round(y_top / _OCR_LINE_BAND_PX) * _OCR_LINE_BAND_PX, x_left)

        lines: list[str] = []
        for entry in sorted(entries, key=_reading_order_key):
            if len(entry) >= 2 and entry[1]:
                text, confidence = entry[1][0], entry[1][1]
                if confidence >= _OCR_MIN_CONFIDENCE:
                    lines.append(text)
        return "\n".join(lines)
