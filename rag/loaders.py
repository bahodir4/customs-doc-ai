"""Source loaders — produce markdown text from a URL or file.

Two concrete loaders:
- `URLLoader`  : fetches a webpage with httpx, strips chrome (nav/footer/
  scripts), converts to markdown with markdownify in ATX heading style.
  For legal documents (lex.uz etc.) where headings are styled via CSS
  rather than `<h1>` tags, falls back to promoting "Глава"/"Статья"/
  "Article"/"Modda" line starts to markdown headers.
- `DocxLoader` : parses a .docx with python-docx, mapping paragraph styles
  (Heading 1/2/3, Заголовок 1/2/3) to `#`, `##`, `###`.

Both implement the `MarkdownLoader` protocol so the ingestion service can
treat them uniformly.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Final, Pattern, Protocol

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify

from core.logging import get_logger

logger = get_logger(__name__)


class MarkdownLoader(Protocol):
    """A loader turns a source identifier into markdown text."""

    async def load(self, source: str) -> str: ...


# ── URL loader ──────────────────────────────────────────────────────


class URLLoader:
    """Fetch a webpage and convert it to markdown.

    Strips navigation, header, footer, scripts, styles, and ASIDE elements
    before conversion. Uses ATX heading style (`# H1`) so the chunker can
    detect headings reliably.

    For legal documents where the page styles headings via CSS classes
    instead of semantic `<h1>` tags (lex.uz, EUR-Lex, etc.),
    `_promote_legal_sections` detects "Глава", "Статья", "Article",
    "Bob", "Modda" patterns at line starts and promotes them to markdown
    headers. This is safe to run unconditionally — it only matches
    lines that aren't already headers.
    """

    _USER_AGENT: Final[str] = "customs-doc-ai/1.0 (+local)"
    _STRIP_TAGS: Final[tuple[str, ...]] = (
        "script", "style", "noscript",
        "nav", "header", "footer", "aside",
        "form", "iframe",
    )

    # Legal-section patterns. Each maps to a markdown heading level.
    # H1 — top-level divisions (Раздел / Section / Boʻlim)
    _H1_PATTERN: Final[Pattern[str]] = re.compile(
        r"^(?:Раздел|Section|Bo[ʻ']?lim|Bolim)\s+[IVXLCDM\d]+",
        re.IGNORECASE,
    )
    # H2 — chapters (Глава / Chapter / Bob)
    _H2_PATTERN: Final[Pattern[str]] = re.compile(
        r"^(?:Глава|Chapter|Bob)\s+\d+",
        re.IGNORECASE,
    )
    # H3 — articles (Статья / Article / Modda)
    _H3_PATTERN: Final[Pattern[str]] = re.compile(
        r"^(?:Статья|Article|Modda)\s+\d+",
        re.IGNORECASE,
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
        for tag in soup(list(self._STRIP_TAGS)):
            tag.decompose()
        # Prefer main/article if the page exposes one — it cuts noise dramatically.
        main = soup.find("main") or soup.find("article") or soup.body or soup
        md = markdownify(str(main), heading_style="ATX", bullets="-")
        md = self._collapse_whitespace(md)
        md = self._promote_legal_sections(md)
        return md

    @staticmethod
    def _collapse_whitespace(text: str) -> str:
        """Trim each line and collapse 3+ blank lines into 2."""
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

    @classmethod
    def _promote_legal_sections(cls, markdown: str) -> str:
        """Promote legal-section markers to markdown headers.

        Only matches lines that aren't already markdown headers, so it's
        safe to run regardless of whether the page already had `<h1>` tags.
        Tracks how many lines were promoted for diagnostic logging.
        """
        out_lines: list[str] = []
        promoted = {"h1": 0, "h2": 0, "h3": 0}

        for line in markdown.split("\n"):
            stripped = line.lstrip()
            # Skip lines that are already headers (markdownify or earlier promotion).
            if stripped.startswith("#"):
                out_lines.append(line)
                continue
            content = stripped.strip()
            if not content:
                out_lines.append(line)
                continue

            if cls._H1_PATTERN.match(content):
                out_lines.append(f"# {content}")
                promoted["h1"] += 1
            elif cls._H2_PATTERN.match(content):
                out_lines.append(f"## {content}")
                promoted["h2"] += 1
            elif cls._H3_PATTERN.match(content):
                out_lines.append(f"### {content}")
                promoted["h3"] += 1
            else:
                out_lines.append(line)

        if any(promoted.values()):
            logger.info(
                "Promoted legal sections: h1=%d, h2=%d, h3=%d",
                promoted["h1"], promoted["h2"], promoted["h3"],
            )
        return "\n".join(out_lines)


# ── DOCX loader ─────────────────────────────────────────────────────


class DocxLoader:
    """Convert a .docx file to markdown by mapping heading styles."""

    # Recognise both English and Russian style names. Word documents
    # produced in localised Office installs use the localised style name
    # internally, even though the underlying paragraph is "Heading 1".
    _STYLE_MAP: Final[dict[str, str]] = {
        "Heading 1": "#",
        "Heading 2": "##",
        "Heading 3": "###",
        "Heading 4": "####",
        "Heading 5": "#####",
        "Heading 6": "######",
        "heading 1": "#", "heading 2": "##", "heading 3": "###",
        "Заголовок 1": "#",
        "Заголовок 2": "##",
        "Заголовок 3": "###",
        "Заголовок 4": "####",
        "Title": "#",
    }

    async def load(self, source: str) -> str:
        # python-docx is sync; the file I/O is local so we keep it simple.
        from docx import Document  # lazy import: heavy native dep

        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"DOCX not found: {path}")

        logger.info("Loading DOCX: %s", path)
        doc = Document(str(path))

        parts: list[str] = []
        for para in doc.paragraphs:
            text = (para.text or "").strip()
            if not text:
                continue
            style_name = para.style.name if para.style else ""
            md_prefix = self._STYLE_MAP.get(style_name)
            if md_prefix:
                parts.append(f"{md_prefix} {text}")
            else:
                parts.append(text)

        # Include table text as plain paragraphs (no markdown table syntax).
        # Customs-law documents rarely depend on table layout for meaning;
        # the text content is what matters for retrieval.
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells)
                if row_text.strip(" |"):
                    parts.append(row_text)

        return "\n\n".join(parts)


# ── Markdown / plain-text loader ────────────────────────────────────


class MarkdownFileLoader:
    """Pass-through loader for `.md` or `.txt` files."""

    async def load(self, source: str) -> str:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        logger.info("Reading markdown file: %s", path)
        return path.read_text(encoding="utf-8")
