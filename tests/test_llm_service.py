"""Smoke tests for LLMService."""
from __future__ import annotations

import json

import pytest

from core.services import LLMResponseError, LLMService


# ── Pure-logic tests (no Ollama needed) ──────────────────────────────


class TestJSONParsing:
    """Verifies the static _parse_json helper handles realistic LLM output."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ('{"a": 1}', {"a": 1}),
            ('```json\n{"a": 1}\n```', {"a": 1}),
            ('```\n{"a": 1}\n```', {"a": 1}),
            ('Here is the JSON:\n{"a": 1}\nDone.', {"a": 1}),
            ('  \n {"a": 1, "b": [2, 3]}  \n', {"a": 1, "b": [2, 3]}),
        ],
    )
    def test_parses_valid_json_variants(self, raw: str, expected: dict) -> None:
        assert LLMService._parse_json(raw) == expected

    def test_raises_on_garbage(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            LLMService._parse_json("not json at all")


# ── Integration tests (require running Ollama) ──────────────────────


@pytest.mark.asyncio
@pytest.mark.integration
async def test_complete_returns_text(llm_service: LLMService) -> None:
    response = await llm_service.complete(
        system="You are a helpful assistant. Reply briefly.",
        user="What is 2 + 2?",
    )
    assert isinstance(response, str)
    assert response.strip()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_complete_json_returns_dict(llm_service: LLMService) -> None:
    result = await llm_service.complete_json(
        system="Return a JSON object with keys 'sum' and 'product'. Only JSON.",
        user="Compute for the numbers 3 and 4.",
    )
    assert isinstance(result, dict)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_complete_json_raises_on_garbage(llm_service: LLMService) -> None:
    with pytest.raises(LLMResponseError):
        await llm_service.complete_json(
            system="Reply with the word 'no' and nothing else.",
            user="hello",
        )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    "text, expected",
    [
        ("Hello, this is an English invoice document.", "en"),
        ("Это таможенная декларация.", "ru"),
        ("Bu O'zbekistondan kelgan hujjat.", "uz"),
    ],
)
async def test_detect_language(
    llm_service: LLMService, text: str, expected: str
) -> None:
    assert await llm_service.detect_language(text) == expected


@pytest.mark.asyncio
@pytest.mark.integration
async def test_detect_intent(llm_service: LLMService) -> None:
    intent = await llm_service.detect_intent(
        "What is the customs duty rate for medical devices in Uzbekistan?"
    )
    assert intent in {"doc_qa", "rag", "hybrid"}
