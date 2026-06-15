"""LLM service.

A single async wrapper around Ollama. Centralises every LLM call so model
choice, retries, parsing, and prompt boilerplate live in one place. Domain
methods (`detect_language`, `detect_intent`, `chat`) have inline prompts.
Document-type-specific prompts (classify, extract) belong in
`core.prompts` (Phase 3) and call `complete_json()` here.

Design notes:
- The client is created in `__init__` but doesn't open connections eagerly;
  ChatOllama uses an HTTP client that's lazy.
- All public methods are `async`. The underlying LangChain client supports
  `ainvoke`, so no thread-pool wrapping is needed.
- JSON parsing is defensive: strips markdown code fences and surrounding
  prose if the model misbehaves.
"""
from __future__ import annotations

import json
import re
from typing import AsyncIterator, Final, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from config.settings import OllamaSettings, OpenAISettings
from core.logging import get_logger

logger = get_logger(__name__)

Language = Literal["uz", "ru", "en"]
Intent = Literal["doc_qa", "rag", "hybrid"]

_VALID_LANGUAGES: Final[frozenset[str]] = frozenset({"uz", "ru", "en"})
_VALID_INTENTS: Final[frozenset[str]] = frozenset({"doc_qa", "rag", "hybrid"})
_JSON_FENCE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^```(?:json)?\s*|\s*```$", re.MULTILINE
)

_LANGUAGE_DETECTION_PROMPT: Final[str] = (
    "You are a language classifier. Read the text and respond with ONE word: "
    "'uz' for Uzbek, 'ru' for Russian, or 'en' for English. "
    "No punctuation, no explanation, just the code."
)

_INTENT_DETECTION_PROMPT: Final[str] = (
    "You are an intent classifier for a customs document Q&A system. "
    "Classify the user question into ONE of:\n"
    "- 'doc_qa' — about a specific uploaded document's fields\n"
    "- 'rag' — about Uzbekistan customs law or regulations\n"
    "- 'hybrid' — requires both the user's documents and customs law\n"
    "Respond with the single label, nothing else."
)

_CHAT_SYSTEM_TEMPLATE: Final[str] = (
    "You are an assistant for Uzbekistan customs document analysis. "
    "Answer the user's question using ONLY the provided context. "
    "If the context is insufficient, say so explicitly. "
    "Respond in the user's language: {language}."
)


class LLMResponseError(Exception):
    """Raised when the LLM returns content that cannot be parsed as expected."""


class LLMService:
    """Async wrapper around the LLM — Ollama or OpenAI, selected at construction."""

    def __init__(
        self,
        ollama_settings: OllamaSettings,
        openai_settings: OpenAISettings | None = None,
        provider: str = "ollama",
    ) -> None:
        self._provider = provider

        if provider == "openai":
            if not openai_settings or not openai_settings.api_key:
                logger.warning(
                    "LLM_PROVIDER=openai but OPENAI_API_KEY is not set — "
                    "falling back to Ollama."
                )
                provider = "ollama"
            else:
                self._client = ChatOpenAI(
                    model=openai_settings.chat_model,
                    api_key=openai_settings.api_key,
                    temperature=openai_settings.temperature,
                    timeout=openai_settings.request_timeout,
                )
                logger.info(
                    "LLMService ready (provider=openai, model=%s)",
                    openai_settings.chat_model,
                )
                return

        # Ollama (default or fallback)
        client_kwargs: dict = (
            {"headers": {"ngrok-skip-browser-warning": "true"}}
            if "ngrok" in ollama_settings.base_url
            else {}
        )
        self._client = ChatOllama(
            base_url=ollama_settings.base_url,
            model=ollama_settings.chat_model,
            temperature=ollama_settings.temperature,
            timeout=ollama_settings.request_timeout,
            client_kwargs=client_kwargs,
        )
        logger.info(
            "LLMService ready (provider=ollama, model=%s, base_url=%s)",
            ollama_settings.chat_model,
            ollama_settings.base_url,
        )

    # ── Primitives ───────────────────────────────────────────────────

    async def complete(self, system: str, user: str) -> str:
        """Run a single LLM completion. Returns the raw text response."""
        messages = [SystemMessage(content=system), HumanMessage(content=user)]
        response = await self._client.ainvoke(messages)
        return str(response.content).strip()

    async def complete_json(self, system: str, user: str) -> dict:
        """Run a completion expected to return JSON.

        Raises LLMResponseError if the response cannot be parsed.
        """
        text = await self.complete(system, user)
        try:
            return self._parse_json(text)
        except json.JSONDecodeError as exc:
            preview = text[:200].replace("\n", " ")
            raise LLMResponseError(
                f"LLM did not return valid JSON: {exc}. Preview: {preview!r}"
            ) from exc

    # ── Domain methods ───────────────────────────────────────────────

    async def detect_language(self, text: str) -> Language:
        """Detect the language of input text. Defaults to 'en' on uncertainty."""
        sample = text[:500]
        if not sample.strip():
            return "en"
        raw = await self.complete(_LANGUAGE_DETECTION_PROMPT, f"Text:\n{sample}")
        token = raw.lower().strip().strip(".,!?'\"")
        if token in _VALID_LANGUAGES:
            return token  # type: ignore[return-value]
        logger.warning("Language detection returned %r; defaulting to 'en'.", raw)
        return "en"

    async def detect_intent(self, question: str) -> Intent:
        """Classify chat question into routing intent. Defaults to 'hybrid'."""
        raw = await self.complete(_INTENT_DETECTION_PROMPT, f"Question:\n{question}")
        token = raw.lower().strip().strip(".,!?'\"")
        if token in _VALID_INTENTS:
            return token  # type: ignore[return-value]
        logger.warning("Intent detection returned %r; defaulting to 'hybrid'.", raw)
        return "hybrid"

    async def chat(self, question: str, context: str, language: Language) -> str:
        """Generate a chat response grounded in retrieved context."""
        system = _CHAT_SYSTEM_TEMPLATE.format(language=language)
        user = f"Context:\n{context}\n\nQuestion: {question}"
        return await self.complete(system, user)

    async def astream_chat(
        self, question: str, context: str, language: str
    ) -> AsyncIterator[str]:
        """Stream a chat response token by token."""
        system = _CHAT_SYSTEM_TEMPLATE.format(language=language)
        user = f"Context:\n{context}\n\nQuestion: {question}"
        messages = [SystemMessage(content=system), HumanMessage(content=user)]
        async for chunk in self._client.astream(messages):
            if chunk.content:
                yield str(chunk.content)

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Extract JSON object from LLM text, tolerating code fences and prose."""
        cleaned = _JSON_FENCE_PATTERN.sub("", text).strip()
        if cleaned.startswith("{") and cleaned.endswith("}"):
            return json.loads(cleaned)
        # Fallback: locate the outermost JSON object.
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise json.JSONDecodeError("No JSON object found", cleaned, 0)
        return json.loads(cleaned[start : end + 1])
