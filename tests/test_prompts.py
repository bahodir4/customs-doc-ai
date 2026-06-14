"""Unit tests for the universal prompt registry."""
from __future__ import annotations

import pytest

from core.prompts import (
    CLASSIFY_LABELS,
    DOC_TYPES,
    get_classify_prompt,
    get_extraction_prompt,
    get_page_items_prompt,
    normalise_classify_response,
)


class TestExtractionPrompt:
    def test_returns_tuple_of_strings(self) -> None:
        system, user = get_extraction_prompt("sample text")
        assert isinstance(system, str) and system.strip()
        assert isinstance(user, str) and user.strip()

    def test_user_prompt_embeds_input_text(self) -> None:
        marker = "MARKER-XYZ-123"
        _, user = get_extraction_prompt(f"hello {marker} world")
        assert marker in user

    def test_system_mentions_json(self) -> None:
        system, _ = get_extraction_prompt("x")
        assert "JSON" in system

    def test_system_mentions_all_sections(self) -> None:
        system, _ = get_extraction_prompt("x")
        # The organiser prompt should guide the LLM to use logical sections
        for keyword in ("parties", "goods", "financials", "logistics"):
            assert keyword in system

    def test_full_text_is_included(self) -> None:
        # No truncation — every byte of OCR text must reach the LLM.
        big = "X" * 100_000
        _, user = get_extraction_prompt(big)
        assert big in user

    def test_per_area_pricing_hint(self) -> None:
        system, _ = get_extraction_prompt("x")
        assert "M2" in system or "100 M2" in system


class TestPageItemsPrompt:
    def test_returns_tuple_of_strings(self) -> None:
        system, user = get_page_items_prompt("page text here")
        assert isinstance(system, str) and system.strip()
        assert isinstance(user, str) and user.strip()

    def test_user_prompt_embeds_page_text(self) -> None:
        marker = "PAGE-MARKER-789"
        _, user = get_page_items_prompt(f"hello {marker}")
        assert marker in user

    def test_returns_items_key(self) -> None:
        _, user = get_page_items_prompt("x")
        assert '"items"' in user

    def test_system_restricts_to_one_page(self) -> None:
        system, _ = get_page_items_prompt("x")
        assert "ONE PAGE" in system or "one page" in system.lower()


class TestClassifyPrompt:
    def test_returns_tuple_of_strings(self) -> None:
        system, user = get_classify_prompt("Some text")
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_system_lists_every_valid_label(self) -> None:
        system, _ = get_classify_prompt("x")
        for label in CLASSIFY_LABELS:
            assert label in system


class TestNormaliseClassifyResponse:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("invoice", "invoice"),
            ("INVOICE", "invoice"),
            (" awb ", "awb"),
            ("gtd.", "gtd"),
            ("cmr,", "cmr"),
            ("packing_list", "packing_list"),
            ("letter", "letter"),
            ("unknown", "unknown"),
            ("invoice — this is a commercial invoice", "invoice"),
            ("hello world", "unknown"),
            ("", "unknown"),
            ("   ", "unknown"),
        ],
    )
    def test_normalisation(self, raw: str, expected: str) -> None:
        assert normalise_classify_response(raw) == expected


class TestDocTypes:
    def test_doc_types_tuple(self) -> None:
        assert "invoice" in DOC_TYPES
        assert "awb" in DOC_TYPES
        assert "gtd" in DOC_TYPES

    def test_classify_labels_superset_of_doc_types(self) -> None:
        for dt in DOC_TYPES:
            assert dt in CLASSIFY_LABELS
        assert "letter" in CLASSIFY_LABELS
        assert "unknown" in CLASSIFY_LABELS
