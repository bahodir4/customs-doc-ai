"""Unit tests for the prompt registry."""
from __future__ import annotations

import pytest

from core.prompts import (
    CLASSIFY_LABELS,
    DOC_TYPES,
    get_classify_prompt,
    get_extraction_prompt,
    normalise_classify_response,
)


class TestExtractionPrompts:
    @pytest.mark.parametrize("doc_type", DOC_TYPES)
    def test_returns_tuple_of_strings(self, doc_type: str) -> None:
        system, user = get_extraction_prompt(doc_type, "sample text")
        assert isinstance(system, str) and system.strip()
        assert isinstance(user, str) and user.strip()

    @pytest.mark.parametrize("doc_type", DOC_TYPES)
    def test_user_prompt_embeds_input_text(self, doc_type: str) -> None:
        marker = "MARKER-XYZ-123"
        _, user = get_extraction_prompt(doc_type, f"hello {marker} world")
        assert marker in user

    @pytest.mark.parametrize("doc_type", DOC_TYPES)
    def test_user_prompt_includes_schema_braces(self, doc_type: str) -> None:
        _, user = get_extraction_prompt(doc_type, "x")
        # Every schema template is a JSON-like object with braces.
        assert "{" in user and "}" in user

    @pytest.mark.parametrize("doc_type", DOC_TYPES)
    def test_system_prompt_mentions_rules(self, doc_type: str) -> None:
        system, _ = get_extraction_prompt(doc_type, "x")
        # The shared rules block uses the word "JSON" — every doc type inherits it.
        assert "JSON" in system

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="No extraction prompt"):
            get_extraction_prompt("phantom_type", "x")

    def test_long_text_is_truncated(self) -> None:
        big = "X" * 100_000
        _, user = get_extraction_prompt("invoice", big)
        # MAX_TEXT_CHARS is 6000 in _base.py; the user prompt should be much
        # shorter than the input.
        assert len(user) < 20_000


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
