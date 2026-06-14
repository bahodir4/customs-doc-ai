"""Database service.

Async PostgreSQL persistence for processed documents. The `Document` ORM
model stores the structured fields produced by the extraction pipeline,
alongside the raw OCR text and any validation errors.

Design notes:
- Uses SQLAlchemy 2.0 typed-mapped style (Mapped[...] + mapped_column).
- One async engine per process; an async_sessionmaker yields sessions
  per-request via an `async with service.session() as s:` pattern.
- Every read returns plain dicts (via `Document.to_dict()`) so callers
  don't depend on the ORM layer.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Final, Optional, Sequence

from sqlalchemy import JSON, DateTime, Index, String, Text, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config.settings import PostgresSettings
from core.logging import get_logger

logger = get_logger(__name__)


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class Document(Base):
    """A processed customs document."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    doc_type: Mapped[str] = mapped_column(String(32), index=True)
    file_name: Mapped[str] = mapped_column(String(512))
    file_path: Mapped[str] = mapped_column(String(1024))
    raw_text: Mapped[str] = mapped_column(Text)
    extracted_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    validation_errors: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="done", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )

    __table_args__ = (
        Index("ix_documents_doc_type_created_at", "doc_type", "created_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Plain-dict view for the API layer."""
        return {
            "id": self.id,
            "doc_type": self.doc_type,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "raw_text": self.raw_text,
            "extracted_data": self.extracted_data,
            "validation_errors": self.validation_errors,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


_VALID_STATUSES: Final[frozenset[str]] = frozenset({"processing", "done", "error"})


class DBService:
    """Async persistence service for documents."""

    def __init__(self, settings: PostgresSettings, *, echo: bool = False) -> None:
        self._settings = settings
        self._engine: AsyncEngine = create_async_engine(
            settings.dsn,
            echo=echo,
            poolclass=NullPool,  # no pool — safe across asyncio.run() calls
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
        )
        logger.info("DBService ready (host=%s, db=%s)", settings.host, settings.db)

    # ── Lifecycle ────────────────────────────────────────────────────

    async def close(self) -> None:
        await self._engine.dispose()

    async def create_tables(self) -> None:
        """Create all tables. Idempotent."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Tables created (or already existed).")

    async def drop_tables(self) -> None:
        """Drop all tables. Tests only — never call in production."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.warning("All tables dropped.")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Async context manager yielding a session with auto-commit/rollback."""
        async with self._session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    # ── CRUD ─────────────────────────────────────────────────────────

    async def save_document(
        self,
        *,
        doc_type: str,
        file_name: str,
        file_path: str,
        raw_text: str,
        extracted_data: dict[str, Any],
        validation_errors: Sequence[str] = (),
        status: str = "done",
    ) -> str:
        """Persist a fully-processed document. Returns its id."""
        if status not in _VALID_STATUSES:
            raise ValueError(f"Invalid status {status!r}. Allowed: {sorted(_VALID_STATUSES)}")

        doc = Document(
            doc_type=doc_type,
            file_name=file_name,
            file_path=file_path,
            raw_text=raw_text,
            extracted_data=extracted_data,
            validation_errors=list(validation_errors),
            status=status,
        )
        async with self.session() as s:
            s.add(doc)
            await s.flush()
            doc_id = doc.id
        logger.info("Saved document %s (type=%s, file=%s).", doc_id, doc_type, file_name)
        return doc_id

    async def get_document(self, doc_id: str) -> Optional[dict[str, Any]]:
        """Fetch a single document by id, or None if not found."""
        async with self.session() as s:
            result = await s.get(Document, doc_id)
            return result.to_dict() if result is not None else None

    async def get_documents(self, doc_ids: Sequence[str]) -> list[dict[str, Any]]:
        """Fetch multiple documents by id. Missing ids are silently dropped."""
        if not doc_ids:
            return []
        async with self.session() as s:
            stmt = select(Document).where(Document.id.in_(list(doc_ids)))
            result = await s.execute(stmt)
            return [doc.to_dict() for doc in result.scalars().all()]

    async def list_documents(
        self,
        *,
        doc_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List documents, optionally filtered by doc_type, newest first."""
        async with self.session() as s:
            stmt = select(Document).order_by(Document.created_at.desc()).limit(limit)
            if doc_type is not None:
                stmt = stmt.where(Document.doc_type == doc_type)
            result = await s.execute(stmt)
            return [doc.to_dict() for doc in result.scalars().all()]

    async def update_extraction(
        self,
        doc_id: str,
        *,
        extracted_data: dict[str, Any],
        validation_errors: Sequence[str] = (),
    ) -> bool:
        """Update extracted JSON for a document (used by the correction UI).

        Returns True if a row was updated.
        """
        async with self.session() as s:
            doc = await s.get(Document, doc_id)
            if doc is None:
                return False
            doc.extracted_data = extracted_data
            doc.validation_errors = list(validation_errors)
        logger.info("Updated extraction for document %s.", doc_id)
        return True

    async def delete_document(self, doc_id: str) -> bool:
        """Delete by id. Returns True if a row was removed."""
        async with self.session() as s:
            doc = await s.get(Document, doc_id)
            if doc is None:
                return False
            await s.delete(doc)
        logger.info("Deleted document %s.", doc_id)
        return True