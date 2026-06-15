"""Customs AI — Chat page (default entry point).

Run with: `streamlit run streamlit_app.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.components import empty_state, sidebar_brand, sidebar_health
from app.services import check_health, list_documents, stream_chat_agent
from app.styles import inject_styles, render_tag

# ── Page config ─────────────────────────────────────────────────────

st.set_page_config(
    page_title="Customs AI · Chat",
    page_icon="🛃",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_styles()

# ── Session state ────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []
if "scope_doc_ids" not in st.session_state:
    st.session_state.scope_doc_ids = []
if "_health_cached" not in st.session_state:
    st.session_state._health_cached = None

# ── Sidebar ──────────────────────────────────────────────────────────

with st.sidebar:
    sidebar_brand()
    st.markdown("---")

    st.markdown(
        "<div style='font-size:0.75rem; font-weight:600; color:#64748b; "
        "text-transform:uppercase; letter-spacing:0.06em; margin-bottom:0.5rem;'>"
        "Conversation scope</div>",
        unsafe_allow_html=True,
    )
    try:
        docs = list_documents(limit=200)
    except Exception as exc:
        st.error(f"Could not load documents:\n\n`{exc}`")
        docs = []

    if docs:
        options = {d["id"]: d for d in docs}
        selected_ids = st.multiselect(
            "Filter by document",
            options=list(options.keys()),
            default=st.session_state.scope_doc_ids,
            format_func=lambda did: (
                f"{options[did]['file_name'][:30]}"
                + (f" · {options[did]['doc_type']}" if options[did].get("doc_type") else "")
            ),
            label_visibility="collapsed",
            placeholder="All documents",
        )
        st.session_state.scope_doc_ids = selected_ids
        st.markdown(
            f"<div style='font-size:0.8125rem; color:#64748b; margin-top:0.25rem;'>"
            f"{'Scoped to ' + str(len(selected_ids)) + ' document(s).' if selected_ids else 'Searching all documents + law.'}"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div style='font-size:0.8125rem; color:#64748b;'>"
            "No documents yet. Use the <strong style='color:#94a3b8;'>Documents</strong> page.</div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    if st.session_state._health_cached is None or st.button(
        "Refresh status", use_container_width=True
    ):
        with st.spinner("Checking services…"):
            st.session_state._health_cached = check_health()
    sidebar_health(st.session_state._health_cached)

    st.markdown("---")

    if st.session_state.messages:
        if st.button("Clear conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

# ── Helpers ──────────────────────────────────────────────────────────

_EXAMPLE_PROMPTS = (
    "What is the customs duty rate for medical diagnostic devices?",
    "Какие документы нужны для импорта в Узбекистан?",
    "Show me the total amount of my latest invoice.",
    "Tibbiy asboblar uchun bojxona to'lovi qancha?",
)


def _render_meta(meta: dict) -> None:
    """Render language / intent / source badges below a message."""
    parts: list[str] = []
    if meta.get("language"):
        parts.append(render_tag(f"🌐 {meta['language'].upper()}", kind="info"))
    if meta.get("intent"):
        parts.append(render_tag(f"🎯 {meta['intent']}", kind="info"))
    sources = meta.get("sources") or []
    if sources:
        parts.append(render_tag(f"📚 {', '.join(sources)}", kind="success"))
    else:
        parts.append(render_tag("📚 no sources", kind="warn"))
    if parts:
        st.markdown(
            "<div style='margin-top:0.625rem; display:flex; gap:0.375rem; flex-wrap:wrap;'>"
            + " ".join(parts)
            + "</div>",
            unsafe_allow_html=True,
        )


def render_message(msg: dict) -> None:
    """Render a stored chat message (no streaming — history only)."""
    role = msg["role"]
    with st.chat_message(role, avatar="👤" if role == "user" else "🤖"):
        st.markdown(msg["content"])
        if role == "assistant" and not msg.get("error"):
            _render_meta(msg)


def _stream_and_store(user_input: str) -> None:
    """Stream the assistant response and append both messages to session state."""
    # Append user message first so it's saved even if the model errors
    st.session_state.messages.append({"role": "user", "content": user_input})

    meta: dict = {}
    try:
        with st.chat_message("assistant", avatar="🤖"):
            # st.write_stream drives the sync generator, returns accumulated text
            response_text = st.write_stream(
                stream_chat_agent(
                    user_input,
                    context_doc_ids=st.session_state.scope_doc_ids or None,
                    meta_out=meta,
                )
            )
            _render_meta(meta)
    except Exception as exc:
        response_text = f"_Error: {type(exc).__name__}: {exc}_"
        meta = {"error": True}
        # Display the error inside the chat bubble
        with st.chat_message("assistant", avatar="🤖"):
            st.markdown(response_text)

    st.session_state.messages.append({
        "role": "assistant",
        "content": response_text or "",
        "language": meta.get("language"),
        "intent": meta.get("intent"),
        "sources": meta.get("sources", []),
        "error": meta.get("error", False),
    })


# ── Empty state with example prompts ─────────────────────────────────

def render_empty_state() -> None:
    empty_state(
        icon="💬",
        title="Customs document intelligence",
        description="Ask questions about your uploaded documents and Uzbek customs law.",
    )
    st.markdown(
        "<div style='text-align:center; font-size:0.8125rem; font-weight:600; "
        "color:var(--c-text-muted); text-transform:uppercase; letter-spacing:0.06em; "
        "margin:1.5rem 0 0.75rem;'>Try a sample question</div>",
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    for i, prompt in enumerate(_EXAMPLE_PROMPTS):
        if cols[i % 2].button(prompt, key=f"ex_{i}", use_container_width=True):
            # Queue the prompt so it goes through the normal streaming path on rerun
            st.session_state.queued_input = prompt
            st.rerun()


# ── Render history ────────────────────────────────────────────────────

if not st.session_state.messages:
    render_empty_state()
else:
    for m in st.session_state.messages:
        render_message(m)

# ── Chat input + queued prompts ───────────────────────────────────────

# `queued_input` is set by example-prompt buttons; chat_input takes live input.
user_input = (
    st.chat_input("Ask about your customs documents or Uzbek law…")
    or st.session_state.pop("queued_input", None)
)

if user_input:
    # Display the user message immediately (before streaming starts)
    with st.chat_message("user", avatar="👤"):
        st.markdown(user_input)

    _stream_and_store(user_input)
