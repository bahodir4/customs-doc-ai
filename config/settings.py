"""Application settings.

Configuration is split into one nested model per concern (Ollama, Qdrant,
Postgres, RAG). Each nested model reads its own environment variables via a
distinct prefix, so adding a new variable means editing exactly one class.

Usage:
    from config import settings

    print(settings.ollama.chat_model)
    print(settings.postgres.dsn)
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
ENV_FILE: Path = PROJECT_ROOT / ".env"


class OpenAISettings(BaseSettings):
    """OpenAI API settings (used when LLM_PROVIDER=openai)."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="OPENAI_",
        extra="ignore",
        case_sensitive=False,
    )

    api_key: str = ""
    chat_model: str = "gpt-4.1-mini"
    temperature: float = 0.0
    request_timeout: float = 60.0


class OllamaSettings(BaseSettings):
    """Ollama (LLM + embeddings) connection settings."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="OLLAMA_",
        extra="ignore",
        case_sensitive=False,
    )

    base_url: str = "http://localhost:11434"
    chat_model: str = "qwen2.5:7b"
    embed_model: str = "bge-m3"
    request_timeout: float = 120.0
    temperature: float = 0.0


class QdrantSettings(BaseSettings):
    """Qdrant vector store settings."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="QDRANT_",
        extra="ignore",
        case_sensitive=False,
    )

    host: str = "localhost"
    port: int = 6333
    grpc_port: int = 6334
    doc_collection: str = "doc_chunks"
    lex_collection: str = "lex_uz"
    embedding_dim: int = 1024

    @computed_field
    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


class PostgresSettings(BaseSettings):
    """PostgreSQL connection settings."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="POSTGRES_",
        extra="ignore",
        case_sensitive=False,
    )

    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str = "postgres"
    db: str = "custdocs"

    @computed_field
    @property
    def dsn(self) -> str:
        """Async DSN compatible with SQLAlchemy + asyncpg."""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.db}"
        )


class RAGSettings(BaseSettings):
    """RAG pipeline settings."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="RAG_",
        extra="ignore",
        case_sensitive=False,
    )

    chunk_size: int = 500
    chunk_overlap: int = 100   # 20% overlap keeps cross-sentence context within a section
    top_k: int = 5


class AppSettings(BaseSettings):
    """Root application settings — aggregates every nested section."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["dev", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    llm_provider: Literal["ollama", "openai"] = "ollama"

    project_root: Path = Field(default=PROJECT_ROOT)
    upload_dir: Path = Field(default=PROJECT_ROOT / "data" / "uploads")

    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    rag: RAGSettings = Field(default_factory=RAGSettings)

    def ensure_directories(self) -> None:
        """Create directories that the app expects to exist."""
        self.upload_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return the cached singleton AppSettings instance.

    Cached so every import gets the same object — avoids reparsing the
    .env file on every call and keeps behaviour deterministic across the
    process.
    """
    return AppSettings()


settings: AppSettings = get_settings()
