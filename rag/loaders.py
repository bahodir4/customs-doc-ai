"""Source loaders — produce clean markdown from a URL or .docx file.

Two concrete loaders:
- `URLLoader`  : fetches a page with httpx, strips chrome and decorative
  elements, converts to markdown, then runs lex.uz-specific cleanup to
  remove icon-button noise (3 000+ triples per document) and reinserts
  paragraph breaks before embedded legal section markers.
- `DocxLoader` : parses a .docx with python-docx in document order
  (paragraphs and tables interleaved), maps heading styles to ATX markdown,
  applies the same legal-section promotion used by the URL loader.

Both implement the `MarkdownLoader` protocol so the ingestion service can
treat them uniformly.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Final, Pattern, Protocol

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify

from core.logging import get_logger

logger = get_logger(__name__)


# ── Shared legal-structure patterns ─────────────────────────────────
# Used by both loaders to promote section/chapter/article lines to ATX
# headings regardless of whether the source is HTML or DOCX.

# H1 — top-level divisions: Раздел / Section / Boʻlim / Qism
_H1_RE: Final[Pattern[str]] = re.compile(
    r"^(?:Раздел|Часть|Section|Part|Bo[ʻ']?lim|Qism)\s+[IVXLCDM\d]+",
    re.IGNORECASE,
)
# H2 — chapters: Глава / Chapter / Bob
_H2_RE: Final[Pattern[str]] = re.compile(
    r"^(?:Глава|Chapter|Bob)\s+\d+",
    re.IGNORECASE,
)
# H3 — articles: Статья / Article / Modda
_H3_RE: Final[Pattern[str]] = re.compile(
    r"^(?:Статья|Article|Modda)\s+\d+",
    re.IGNORECASE,
)

# Matches a legal marker that is NOT at the start of a line — used to
# inject \n\n before it so the line-start patterns above fire correctly.
_EMBEDDED_SECTION_RE: Final[Pattern[str]] = re.compile(
    r"(?<=[^\n])\s*"
    r"("
    r"(?:Раздел|Часть|Глава|Статья"
    r"|Section|Part|Chapter|Article"
    r"|Bob|Bo[ʻ']?lim|Qism|Modda)"
    r"\s+[IVXLCDM\d]+"
    r")",
    re.IGNORECASE,
)

# lex.uz icon-triple: the three action buttons (comment / audio / link) that
# appear between EVERY structural element on lex.uz — before the title, between
# title and body, and after the body.  They are the visual separator on the page
# so we REPLACE them with \n\n (not delete) to restore paragraph structure.
# Pattern allows the img refs to be present or already stripped.
_LEXUZ_TRIPLE_RE: Final[Pattern[str]] = re.compile(
    r"(?:!\[[^\]]*\]\(/img/cmt\.svg\))?"
    r"Ҳужжатга таклиф юбориш"
    r"(?:!\[[^\]]*\]\(/img/vlm\.svg\))?"
    r"Аудиони тинглаш"
    r"(?:!\[[^\]]*\]\(/img/lnk\.svg\))?"
    r"Ҳужжат элементидан ҳавола олиш",
    re.UNICODE,
)

# Fallback: individual lex.uz noise strings not covered by the triple.
_LEXUZ_NOISE_RE: Final[Pattern[str]] = re.compile(
    r"(?:"
    r"Ҳужжатга таклиф юбориш"
    r"|Аудиони тинглаш"
    r"|Ҳужжат элементидан ҳавола олиш"
    r"|Комментарий\s+LexUz"
    r")",
    re.UNICODE | re.IGNORECASE,
)

# Residual markdown image references left after stripping <img> elements.
_MD_IMAGE_RE: Final[Pattern[str]] = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def _promote_legal_sections(text: str) -> str:
    """Promote Статья / Глава / Раздел lines to ATX heading markers.

    Only matches lines that are not already markdown headers, so it is safe
    to call on text that already has some headings from DOCX style mapping.
    """
    out: list[str] = []
    promoted = {"h1": 0, "h2": 0, "h3": 0}
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            out.append(line)
            continue
        if _H1_RE.match(stripped):
            out.append(f"# {stripped}")
            promoted["h1"] += 1
        elif _H2_RE.match(stripped):
            out.append(f"## {stripped}")
            promoted["h2"] += 1
        elif _H3_RE.match(stripped):
            out.append(f"### {stripped}")
            promoted["h3"] += 1
        else:
            out.append(line)
    if any(promoted.values()):
        logger.info(
            "Promoted legal sections: h1=%d h2=%d h3=%d",
            promoted["h1"], promoted["h2"], promoted["h3"],
        )
    return "\n".join(out)


def _clean_legal_markdown(text: str) -> str:
    """Remove lex.uz UI noise and restore paragraph structure.

    Order matters:
    1. Replace the lex.uz icon-triple with \\n\\n.
       The triple (comment/audio/link buttons) is a structural separator on
       the page — it appears between every adjacent pair of elements (before
       the title, between title and body, after the body).  Replacing it
       with a blank line instead of deleting it restores the paragraph
       breaks that are lost when the whole page renders as one block.
    2. Strip all residual markdown image refs.
    3. Strip any remaining individual lex.uz UI labels (fallback).
    4. Collapse multiple spaces within a line.
    5. Inject \\n\\n before legal markers still embedded mid-line.
    6. Collapse runs of 3+ blank lines to 2.
    """
    # 1. Icon-triple → paragraph break (the key structural fix)
    text = _LEXUZ_TRIPLE_RE.sub("\n\n", text)
    # 2. Residual image refs
    text = _MD_IMAGE_RE.sub("", text)
    # 3. Any stray individual UI labels
    text = _LEXUZ_NOISE_RE.sub("", text)
    # 4. Multiple spaces → single space
    text = re.sub(r"[ \t]{2,}", " ", text)
    # 5. Embedded legal markers → own paragraph
    text = _EMBEDDED_SECTION_RE.sub(r"\n\n\1", text)
    # 6. Normalise blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _collapse_whitespace(text: str) -> str:
    """Trim line-trailing whitespace and cap consecutive blanks at 2."""
    lines = [line.rstrip() for line in text.splitlines()]
    result: list[str] = []
    blank_run = 0
    for line in lines:
        if not line:
            blank_run += 1
            if blank_run <= 2:
                result.append("")
        else:
            blank_run = 0
            result.append(line)
    return "\n".join(result).strip()


class MarkdownLoader(Protocol):
    async def load(self, source: str) -> str: ...


# ── URL loader ──────────────────────────────────────────────────────


class URLLoader:
    """Fetch a webpage and convert it to clean markdown.

    Pipeline:
      1. httpx GET
      2. BeautifulSoup: remove <script>, <style>, <nav>, <header>, <footer>,
         <aside>, <form>, <iframe>, and ALL <img> elements (icon noise).
      3. markdownify (ATX headings, no img output).
      4. _clean_legal_markdown: strip lex.uz UI button labels, reinsert
         paragraph breaks before embedded section/chapter/article markers.
      5. _collapse_whitespace.
      6. _promote_legal_sections: promote Раздел/Глава/Статья lines to ATX.
    """

    _USER_AGENT: Final[str] = "customs-doc-ai/1.0 (+local)"
    _STRIP_TAGS: Final[tuple[str, ...]] = (
        "script", "style", "noscript",
        "nav", "header", "footer", "aside",
        "form", "iframe",
    )

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout

    async def load(self, source: str) -> str:
        logger.info("Fetching URL: %s", source)
        async with httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            headers={"User-Agent": self._USER_AGENT},
        ) as client:
            response = await client.get(source)
            response.raise_for_status()
        return self._html_to_markdown(response.text)

    def _html_to_markdown(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")

        # Remove structural chrome
        for tag in soup(list(self._STRIP_TAGS)):
            tag.decompose()

        # Remove ALL img elements — they are icons/decorations on legal sites;
        # for text-based RAG the alt text adds no value and the src produces
        # markdown image refs that pollute retrieval.
        for img in soup.find_all("img"):
            img.decompose()

        # Prefer a semantic content container to cut page-level chrome.
        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find(id=re.compile(r"content|main|body|doc", re.I))
            or soup.find(class_=re.compile(r"content|main|body|doc", re.I))
            or soup.body
            or soup
        )

        md = markdownify(str(main), heading_style="ATX", bullets="-", strip=["img"])
        md = _clean_legal_markdown(md)
        md = _collapse_whitespace(md)
        md = _promote_legal_sections(md)
        return md


# ── DOCX loader ─────────────────────────────────────────────────────


class DocxLoader:
    """Convert a .docx file to markdown preserving reading order.

    Walks the body XML in element order (paragraphs and tables
    interleaved) so content inside table cells is not reordered to the
    end of the document.

    Heading detection is two-pass:
      1. Named style map (English + Russian + Uzbek style names).
      2. Heuristic: bold paragraph whose text is ≤ 120 chars and contains
         a legal-section keyword → treated as heading.

    The same _promote_legal_sections and _clean_legal_markdown steps used
    by URLLoader are applied at the end so DOCX exports from lex.uz or
    similar portals receive the same noise-removal treatment.
    """

    _STYLE_MAP: Final[dict[str, str]] = {
        # English
        "Heading 1": "#",  "Heading 2": "##",  "Heading 3": "###",
        "Heading 4": "####", "Heading 5": "#####",
        "heading 1": "#",  "heading 2": "##",  "heading 3": "###",
        "Title": "#",      "Subtitle": "##",
        # Russian
        "Заголовок 1": "#",  "Заголовок 2": "##",  "Заголовок 3": "###",
        "Заголовок 4": "####",
        "Название": "#",
        # Uzbek (some localised Word installs)
        "Sarlavha 1": "#",  "Sarlavha 2": "##",  "Sarlavha 3": "###",
        "Sarlavha": "#",
    }

    async def load(self, source: str) -> str:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"DOCX not found: {path}")
        logger.info("Loading DOCX: %s", path)
        return await asyncio.to_thread(self._convert, path)

    def _convert(self, path: Path) -> str:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = Document(str(path))
        parts: list[str] = []

        for element in doc.element.body:
            local = element.tag.split("}")[-1] if "}" in element.tag else element.tag

            if local == "p":
                para = Paragraph(element, doc)
                text = (para.text or "").strip()
                if not text:
                    continue
                prefix = self._heading_prefix(para)
                if prefix:
                    parts.append(f"{prefix} {text}")
                else:
                    parts.append(text)

            elif local == "tbl":
                table = Table(element, doc)
                seen: set[str] = set()
                for row in table.rows:
                    cells: list[str] = []
                    for cell in row.cells:
                        ct = cell.text.strip()
                        if ct and ct not in seen:
                            cells.append(ct)
                            seen.add(ct)
                    row_text = " | ".join(cells)
                    if row_text:
                        parts.append(row_text)

        raw = "\n\n".join(parts)
        raw = _clean_legal_markdown(raw)
        raw = _collapse_whitespace(raw)
        raw = _promote_legal_sections(raw)
        return raw

    def _heading_prefix(self, para) -> str:
        """Return ATX prefix for a paragraph, or '' if it is body text."""
        style_name = para.style.name if para.style else ""
        # 1. Named style map
        if style_name in self._STYLE_MAP:
            return self._STYLE_MAP[style_name]
        # 2. Heuristic: bold + short + legal keyword → treat as heading
        text = (para.text or "").strip()
        if (
            len(text) <= 120
            and self._is_bold(para)
            and (_H1_RE.match(text) or _H2_RE.match(text) or _H3_RE.match(text))
        ):
            return "###"
        return ""

    @staticmethod
    def _is_bold(para) -> bool:
        """True if the paragraph has at least one bold run."""
        return any(
            run.bold
            for run in para.runs
            if run.text.strip()
        )


# ── Plain-text / markdown file loader ───────────────────────────────


class MarkdownFileLoader:
    """Pass-through loader for .md or .txt files."""

    async def load(self, source: str) -> str:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        logger.info("Reading markdown file: %s", path)
        text = path.read_text(encoding="utf-8")
        # Apply the same cleanup in case the file was exported from a web portal.
        text = _clean_legal_markdown(text)
        text = _collapse_whitespace(text)
        text = _promote_legal_sections(text)
        return text
