"""Reusable Streamlit components."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import streamlit as st

from app.services import HealthStatus
from app.styles import render_status_pill


# ── Empty state ─────────────────────────────────────────────────────


def empty_state(
    *,
    icon: str,
    title: str,
    description: str,
    cta: str | None = None,
) -> None:
    """Render a centered empty-state card."""
    extra = f"<p style='font-size:0.95rem'>{cta}</p>" if cta else ""
    st.markdown(
        f"""
        <div class="empty-state">
            <div style="font-size:3rem; margin-bottom:1rem;">{icon}</div>
            <h2>{title}</h2>
            <p>{description}</p>
            {extra}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Sidebar pieces ──────────────────────────────────────────────────


def sidebar_brand() -> None:
    """Top-of-sidebar logo/title."""
    st.markdown(
        """
        <div style="padding-bottom:1rem;">
            <h2 style="margin:0; font-size:1.25rem;">🛃 Customs AI</h2>
            <p style="margin:0; font-size:0.8rem; color:#71717a;">
                Self-hosted document intelligence
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_health(health: HealthStatus) -> None:
    """Render coloured status pills for each backend service."""
    st.markdown("**System status**")
    pills = (
        render_status_pill("Ollama", health.ollama)
        + "<br/>"
        + render_status_pill("Qdrant", health.qdrant)
        + "<br/>"
        + render_status_pill("Postgres", health.postgres)
    )
    st.markdown(pills, unsafe_allow_html=True)


# ── Document cards ──────────────────────────────────────────────────


def format_timestamp(value: Any) -> str:
    """Best-effort 'time ago' formatting for created_at fields."""
    if value is None:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if not isinstance(value, datetime):
        return str(value)
    now = datetime.now(timezone.utc) if value.tzinfo else datetime.now()
    delta = now - value
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} h ago"
    if seconds < 604800:
        return f"{seconds // 86400} d ago"
    return value.strftime("%Y-%m-%d")


def status_badge(status: str) -> str:
    """Return tag HTML for a doc status."""
    mapping = {
        "done": ("tag-success", "✓ Done"),
        "error": ("tag-error", "× Error"),
        "processing": ("tag-warn", "● Processing"),
    }
    cls, label = mapping.get(status, ("", status))
    return f'<span class="tag {cls}">{label}</span>'


def doc_type_badge(doc_type: str) -> str:
    return f'<span class="tag tag-info">{doc_type}</span>'
