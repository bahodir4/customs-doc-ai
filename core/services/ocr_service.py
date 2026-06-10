"""OCR service.

Extracts text from PDFs and images using a smart routing strategy:

- PDFs are first probed for an embedded text layer via PyMuPDF. If the layer
  is rich enough (digital-born PDFs), that text is returned directly — much
  faster and more accurate than OCR.
- PDFs without a text layer (scanned) and image files (jpg/png) are run
  through PaddleOCR.

PaddleOCR is initialised lazily on first use because model loading is slow
(~5 s) and we don't want that hit on import.
"""
from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import fitz  # PyMuPDF
from PIL import Image

from core.logging import get_logger

logger = get_logger(__name__)

_SUPPORTED_IMAGE_EXT: Final[frozenset[str]] = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"})
_PDF_EXT: Final[str] = ".pdf"
_MIN_TEXT_CHARS_PER_PAGE: Final[int] = 50  # below this we assume scanned
_OCR_RENDER_DPI: Final[int] = 200


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Outcome of a single OCR run."""

    text: str
    page_count: int
    ocr_used: bool       # False = PDF text layer; True = PaddleOCR fallback
    source_path: Path


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
            # Import here so PaddleOCR doesn't load at module import time.
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
        """Try the embedded text layer first; fall back to OCR if sparse."""
        text_layer, page_count = await asyncio.to_thread(self._read_pdf_text_layer, path)
        if self._is_text_layer_sufficient(text_layer, page_count):
            logger.info("PDF text layer used (%d pages, %d chars).", page_count, len(text_layer))
            return ExtractionResult(
                text=text_layer,
                page_count=page_count,
                ocr_used=False,
                source_path=path,
            )

        logger.info("PDF text layer insufficient — running PaddleOCR (%d pages).", page_count)
        ocr_text = await asyncio.to_thread(self._ocr_pdf_pages, path)
        return ExtractionResult(
            text=ocr_text,
            page_count=page_count,
            ocr_used=True,
            source_path=path,
        )

    async def _extract_image(self, path: Path) -> ExtractionResult:
        """OCR a single image file."""
        text = await asyncio.to_thread(self._ocr_image_file, path)
        return ExtractionResult(
            text=text,
            page_count=1,
            ocr_used=True,
            source_path=path,
        )

    @staticmethod
    def _read_pdf_text_layer(path: Path) -> tuple[str, int]:
        """Synchronous helper: read all text from PDF's embedded layer."""
        parts: list[str] = []
        with fitz.open(path) as doc:
            page_count = doc.page_count
            for page in doc:
                parts.append(page.get_text())
        return "\n".join(parts), page_count

    def _is_text_layer_sufficient(self, text: str, page_count: int) -> bool:
        """Heuristic: at least N chars per page on average."""
        if not text.strip() or page_count == 0:
            return False
        return len(text) >= _MIN_TEXT_CHARS_PER_PAGE * page_count

    def _ocr_pdf_pages(self, path: Path) -> str:
        """Render each PDF page at OCR DPI and run PaddleOCR on each."""
        engine = self._get_engine()
        parts: list[str] = []
        with fitz.open(path) as doc:
            for page_idx, page in enumerate(doc, start=1):
                pix = page.get_pixmap(dpi=_OCR_RENDER_DPI)
                image_bytes = pix.tobytes("png")
                page_text = self._ocr_image_bytes(engine, image_bytes)
                if page_text:
                    parts.append(f"--- Page {page_idx} ---\n{page_text}")
        return "\n\n".join(parts)

    def _ocr_image_file(self, path: Path) -> str:
        """OCR a single image from disk."""
        engine = self._get_engine()
        return self._ocr_image_bytes(engine, path.read_bytes())

    @staticmethod
    def _ocr_image_bytes(engine, image_bytes: bytes) -> str:  # noqa: ANN001
        """Run PaddleOCR on raw image bytes; return concatenated text."""
        # PaddleOCR accepts numpy arrays; convert via PIL for robustness.
        import numpy as np

        with Image.open(io.BytesIO(image_bytes)) as img:
            img_rgb = img.convert("RGB")
            arr = np.array(img_rgb)

        result = engine.ocr(arr, cls=True)
        if not result or not result[0]:
            return ""

        lines: list[str] = []
        for entry in result[0]:
            # Each entry: [bbox, (text, confidence)]
            if len(entry) >= 2 and entry[1]:
                lines.append(entry[1][0])
        return "\n".join(lines)
