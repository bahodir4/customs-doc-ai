"""Ask the chat agent a question.

Single-shot CLI for the chat agent. Detects language, routes by intent
(doc_qa / rag / hybrid), retrieves from the appropriate sources, and
prints the response.

Examples:
    python scripts/chat_with_docs.py "What is the customs duty for medical devices?"
    python scripts/chat_with_docs.py "Какова сумма счёта HQPL00073841?"
    python scripts/chat_with_docs.py "Tell me about my invoice" --doc-ids abc-123 def-456
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from core.logging import configure_logging, get_logger
from core.pipeline import build_chat_agent
from core.services import DBService, LLMService, VectorStoreService

logger = get_logger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ask the customs-doc chat agent a question.",
    )
    parser.add_argument("question", type=str, help="Your question (any of: en, ru, uz)")
    parser.add_argument(
        "--doc-ids", nargs="*", default=[],
        help="Optional document ids to scope the question to",
    )
    return parser.parse_args()


def _print_result(result: dict) -> None:
    print()
    print("─" * 70)
    print(result.get("final_response", "(no response)"))
    print("─" * 70)
    print(f"Language : {result.get('detected_language', '?')}")
    print(f"Intent   : {result.get('intent', '?')}")
    sources = result.get("sources_used") or []
    print(f"Sources  : {', '.join(sources) if sources else '(none)'}")


async def main() -> int:
    args = _parse_args()
    configure_logging(settings.log_level)

    llm = LLMService(settings.ollama)
    vector = VectorStoreService(settings.qdrant, settings.ollama)
    db = DBService(settings.postgres)

    try:
        agent = build_chat_agent(llm, vector, db)
        logger.info("Asking: %s", args.question)
        result = await agent.ainvoke({
            "user_input": args.question,
            "context_doc_ids": args.doc_ids,
        })
        _print_result(result)
        return 0
    finally:
        await vector.close()
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
