"""Reusable Streamlit UI components."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import streamlit as st

from app.services import HealthStatus
from app.styles import render_status_pill, render_tag


# ── Empty state ─────────────────────────────────────────────────────


def empty_state(
    *,
    icon: str,
    title: str,
    description: str,
    cta: str | None = None,
) -> None:
    """Centered empty-state with icon tile, heading, and description."""
    extra = f"<p style='margin-top:1rem; font-size:0.875rem;'>{cta}</p>" if cta else ""
    st.markdown(
        f"""
        <div class="empty-state">
            <div class="empty-state-icon">{icon}</div>
            <h2>{title}</h2>
            <p>{description}</p>
            {extra}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Sidebar pieces ──────────────────────────────────────────────────


def sidebar_brand() -> None:
    """Top-of-sidebar product brand block."""
    st.markdown(
        """
        <div style="padding: 0.5rem 0 1.25rem;">
            <div style="display:flex; align-items:center; gap:0.625rem; margin-bottom:0.375rem;">
                <div style="
                    width:32px; height:32px;
                    border-radius:8px;
                    background: linear-gradient(135deg, #6366f1 0%, #818cf8 100%);
                    display:flex; align-items:center; justify-content:center;
                    font-size:1rem; flex-shrink:0;
                    box-shadow: 0 2px 6px rgba(99,102,241,0.35);
                ">🛃</div>
                <div>
                    <div style="
                        font-size:0.9375rem;
                        font-weight:700;
                        color:#f1f5f9;
                        letter-spacing:-0.01em;
                        line-height:1.2;
                    ">Customs AI</div>
                    <div style="
                        font-size:0.7rem;
                        color:#64748b;
                        font-weight:500;
                        letter-spacing:0.04em;
                        text-transform:uppercase;
                    ">Document Intelligence</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_health(health: HealthStatus) -> None:
    """Render coloured status pills for each backend service."""
    st.markdown(
        "<div style='font-size:0.75rem; font-weight:600; color:#64748b; "
        "text-transform:uppercase; letter-spacing:0.06em; margin-bottom:0.5rem;'>"
        "System status</div>",
        unsafe_allow_html=True,
    )
    pills = (
        render_status_pill("Ollama", health.ollama)
        + render_status_pill("Qdrant", health.qdrant)
        + render_status_pill("Postgres", health.postgres)
    )
    st.markdown(pills, unsafe_allow_html=True)


# ── Document metadata helpers ───────────────────────────────────────


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
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 604800:
        return f"{seconds // 86400}d ago"
    return value.strftime("%b %d, %Y")


def status_badge(status: str) -> str:
    """Return badge HTML for a document processing status."""
    mapping = {
        "done":       ("tag-success", "● Done"),
        "error":      ("tag-error",   "✕ Error"),
        "processing": ("tag-warn",    "◌ Processing"),
    }
    cls, label = mapping.get(status, ("", status))
    return f'<span class="tag {cls}">{label}</span>'


def doc_type_badge(doc_type: str) -> str:
    """Return badge HTML for a document type label."""
    return f'<span class="tag tag-purple">{doc_type}</span>'


def ocr_quality_badge(quality: dict | None) -> str:
    """Return badge HTML for an OCR quality dict (supports raw/corrected structure)."""
    if not quality:
        return ""

    _RATING_MAP = {
        "GOOD":       ("tag-success", "Good"),
        "DEGRADED":   ("tag-warn",    "Degraded"),
        "UNREADABLE": ("tag-error",   "Unreadable"),
        "UNKNOWN":    ("",            "?"),
    }

    # New structure: {"raw": {...}, "corrected": {...}}
    if "raw" in quality and "corrected" in quality:
        raw = quality["raw"]
        cor = quality["corrected"]
        r_rating = (raw.get("rating") or "UNKNOWN").upper()
        c_rating = (cor.get("rating") or "UNKNOWN").upper()
        r_pct = raw.get("readable_pct", "")
        c_pct = cor.get("readable_pct", "")
        r_cls, r_lbl = _RATING_MAP.get(r_rating, ("", r_rating))
        c_cls, c_lbl = _RATING_MAP.get(c_rating, ("", c_rating))
        tip = f"Raw: {r_pct}% → Corrected: {c_pct}%"
        # Badge colour driven by the raw scan quality
        badge_cls = r_cls
        label = f"🔬 {r_lbl} → {c_lbl}"
        return f'<span class="tag {badge_cls}" title="{tip}">{label}</span>'

    # Legacy single-assessment structure
    rating = (quality.get("rating") or "UNKNOWN").upper()
    pct = quality.get("readable_pct")
    cls, lbl = _RATING_MAP.get(rating, ("", rating))
    tip = f"{pct}%" if pct is not None else ""
    return f'<span class="tag {cls}" title="{tip}">🔬 OCR: {lbl}</span>'


def doc_card_header(doc: dict) -> str:
    """Return HTML for a document expander header with badges and timestamp."""
    name = doc.get("file_name", "Unknown")
    ts = format_timestamp(doc.get("created_at"))
    s_badge = status_badge(doc.get("status", "?"))
    t_badge = doc_type_badge(doc.get("doc_type", "?")) if doc.get("doc_type") else ""
    quality = (doc.get("extracted_data") or {}).get("_ocr_quality")
    q_badge = ocr_quality_badge(quality)
    return (
        f'<div class="doc-header">'
        f'<span class="doc-name">{name}</span>'
        f'<div class="doc-meta">'
        f'{s_badge}&nbsp;{t_badge}&nbsp;{q_badge}'
        f'<span style="margin-left:0.5rem; color:var(--c-text-subtle);">{ts}</span>'
        f'</div>'
        f'</div>'
    )
