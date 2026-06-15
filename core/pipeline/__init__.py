"""LangGraph pipeline package.

Two compiled graphs:
- `build_doc_pipeline(ocr, llm, vector, db)` — processes uploaded files.
- `build_chat_agent(llm, vector, db)` — answers user questions.

Both take service objects via constructor injection so they're testable
with mocks and decoupled from settings.
"""
from core.pipeline.chat_agent import build_chat_agent, build_retrieval_pipeline
from core.pipeline.doc_pipeline import build_doc_pipeline
from core.pipeline.state import ChatState, DocProcessingState

__all__ = [
    "ChatState",
    "DocProcessingState",
    "build_chat_agent",
    "build_doc_pipeline",
    "build_retrieval_pipeline",
]
