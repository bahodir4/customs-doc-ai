"""Verify that all backing infrastructure services are reachable.

Run this after `docker compose up -d` to confirm Qdrant, PostgreSQL,
and Ollama are accepting connections and that the required models
have been pulled.

Exit code: 0 if everything is healthy, 1 otherwise.
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

# Make the project root importable when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
import httpx

from config import settings

CheckFn = Callable[[], Awaitable[str]]


@dataclass(frozen=True)
class HealthCheck:
    """A single named connectivity probe."""

    name: str
    probe: CheckFn


class InfraHealthChecker:
    """Runs a fixed set of probes against the infrastructure services.

    Each probe is async and returns a short human-readable status string
    on success or raises an exception on failure.
    """

    _CONNECT_TIMEOUT: float = 5.0

    def __init__(self) -> None:
        self._checks: list[HealthCheck] = [
            HealthCheck("Qdrant", self._probe_qdrant),
            HealthCheck("PostgreSQL", self._probe_postgres),
            HealthCheck("Ollama", self._probe_ollama),
        ]

    async def _probe_qdrant(self) -> str:
        url = f"{settings.qdrant.url}/healthz"
        async with httpx.AsyncClient(timeout=self._CONNECT_TIMEOUT) as client:
            response = await client.get(url)
            response.raise_for_status()
        return f"reachable at {settings.qdrant.url}"

    async def _probe_postgres(self) -> str:
        conn = await asyncpg.connect(
            host=settings.postgres.host,
            port=settings.postgres.port,
            user=settings.postgres.user,
            password=settings.postgres.password,
            database=settings.postgres.db,
            timeout=self._CONNECT_TIMEOUT,
        )
        try:
            version: str = await conn.fetchval("SELECT version()")
        finally:
            await conn.close()
        # version looks like: "PostgreSQL 16.3 on x86_64-pc-linux-musl, ..."
        return version.split(",")[0]

    async def _probe_ollama(self) -> str:
        url = f"{settings.ollama.base_url}/api/tags"
        async with httpx.AsyncClient(timeout=self._CONNECT_TIMEOUT) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()

        # Ollama returns model names with explicit tags (e.g. "bge-m3:latest").
        # The user configures names with or without the ":latest" suffix.
        # Normalise both sides so the comparison is tag-aware but lenient.
        installed = {self._normalise_model(m["name"]) for m in payload.get("models", [])}
        required = {
            self._normalise_model(settings.ollama.chat_model),
            self._normalise_model(settings.ollama.embed_model),
        }
        missing = required - installed

        if missing:
            missing_str = ", ".join(sorted(missing))
            return (
                f"reachable but missing model(s): {missing_str} — "
                f"run `docker exec customs-ollama ollama pull <name>`"
            )
        return f"{len(installed)} model(s): {', '.join(sorted(installed))}"

    @staticmethod
    def _normalise_model(name: str) -> str:
        """Add ':latest' if no tag is present, so comparison is consistent."""
        return name if ":" in name else f"{name}:latest"

    async def run(self) -> bool:
        """Execute all probes and print a status line per service.

        Returns True iff every probe succeeded.
        """
        all_passed = True
        for check in self._checks:
            try:
                status = await check.probe()
                print(f"  [OK]   {check.name:<12} {status}")
            except Exception as exc:
                print(
                    f"  [FAIL] {check.name:<12} "
                    f"{type(exc).__name__}: {exc}"
                )
                all_passed = False
        return all_passed


async def main() -> int:
    print("Checking infrastructure services...\n")
    ok = await InfraHealthChecker().run()
    print()
    if ok:
        print("All services healthy.")
        return 0
    print("One or more services unreachable. Check `docker compose ps`.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
