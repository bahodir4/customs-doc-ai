"""OCR quality assessment prompt."""
from __future__ import annotations

_QUALITY_SYSTEM = """\
You are an OCR quality evaluator for customs and trade documents.
Analyze the extracted text and return a JSON quality assessment.

Return ONLY valid JSON with exactly these keys:
{
  "rating": "GOOD" | "DEGRADED" | "UNREADABLE",
  "confidence": <float 0.0–1.0>,
  "readable_pct": <integer 0–100>,
  "issues": [<list of short issue strings, empty if none>]
}

Rating criteria:
- GOOD        : text is clean, numbers and words correctly formed, < 5 % noise
- DEGRADED    : garbled words, broken numbers, split words or character substitutions \
(0↔O, 1↔l↔I), but the main content is still recoverable  (5–35 % noise)
- UNREADABLE  : > 35 % noise; critical fields (amounts, dates, reference numbers) \
are corrupted or missing

Common issues to detect:
  "garbled_words"       – e.g. "lnv0ice", "T0TAL"
  "broken_numbers"      – e.g. "1 2 3 4" instead of "1234"
  "missing_spaces"      – words run together
  "character_subs"      – 0/O or 1/l/I confusion
  "cyrillic_latin_mix"  – Cyrillic and Latin chars mixed in same word
  "low_density"         – very little text for the page count (likely scanned image)
"""


def ocr_quality_prompt(raw_text: str) -> str:
    sample = raw_text[:2500]
    return f"Assess the OCR quality of this extracted text:\n\n{sample}"


__all__ = ["_QUALITY_SYSTEM", "ocr_quality_prompt"]
