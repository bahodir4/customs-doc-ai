"""Customs AI — Chat page (default entry point).

Run with: `streamlit run streamlit_app.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Make project importable from this script location
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.components import empty_state, sidebar_brand, sidebar_health
from app.services import ask_chat_agent, check_health, list_documents
from app.styles import inject_styles, render_tag

# ── Page config ─────────────────────────────────────────────────────


st.set_page_config(
    page_title="Customs AI · Chat",
    page_icon="🛃",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_styles()


# ── Session state init ──────────────────────────────────────────────


if "messages" not in st.session_state:
    st.session_state.messages = []
if "scope_doc_ids" not in st.session_state:
    st.session_state.scope_doc_ids = []
if "_health_cached" not in st.session_state:
    st.session_state._health_cached = None


# ── Sidebar ─────────────────────────────────────────────────────────


with st.sidebar:
    sidebar_brand()
    st.markdown("---")

    st.markdown("**Conversation scope**")
    try:
        docs = list_documents(limit=200)
    except Exception as exc:
        st.error(f"Could not load documents:\n\n`{exc}`")
        st.caption(
            "Check that Postgres is running and that the credentials in "
            "`.env` match `docker-compose.yml`."
        )
        docs = []

    if docs:
        options = {d["id"]: d for d in docs}
        selected_ids = st.multiselect(
            "Filter by document",
            options=list(options.keys()),
            default=st.session_state.scope_doc_ids,
            format_func=lambda did: f"{options[did]['file_name'][:32]}"
            + (f" · {options[did]['doc_type']}" if options[did].get("doc_type") else ""),
            label_visibility="collapsed",
            placeholder="All documents",
        )
        st.session_state.scope_doc_ids = selected_ids
        if selected_ids:
            st.caption(f"Scoped to {len(selected_ids)} document(s).")
        else:
            st.caption("Searching across all documents + customs law.")
    else:
        st.caption("No documents uploaded yet. Use the **Documents** page.")

    st.markdown("---")

    # Health pills — cached on first render, manual refresh button
    if st.session_state._health_cached is None or st.button(
        "Refresh status", use_container_width=True
    ):
        with st.spinner("Checking services..."):
            st.session_state._health_cached = check_health()
    sidebar_health(st.session_state._health_cached)

    st.markdown("---")
    if st.session_state.messages and st.button(
        "Clear conversation", use_container_width=True
    ):
        st.session_state.messages = []
        st.rerun()


# ── Main column ─────────────────────────────────────────────────────


_EXAMPLE_PROMPTS = (
    "What is the customs duty rate for medical diagnostic devices?",
    "Какие документы нужны для импорта в Узбекистан?",
    "Show me the total amount of my latest invoice.",
    "Tibbiy asboblar uchun bojxona to'lovi qancha?",
)


def render_empty_state() -> None:
    empty_state(
        icon="💬",
        title="Customs document intelligence",
        description="Ask questions about your uploaded documents and Uzbek customs law.",
    )
    st.markdown("##### Try one of these")
    cols = st.columns(2)
    for i, prompt in enumerate(_EXAMPLE_PROMPTS):
        if cols[i % 2].button(prompt, key=f"ex_{i}", use_container_width=True):
            _submit(prompt)
            st.rerun()


def _submit(prompt: str) -> None:
    """Add a user message and run the agent, appending the response."""
    st.session_state.messages.append({"role": "user", "content": prompt})

    try:
        result = ask_chat_agent(
            prompt, context_doc_ids=st.session_state.scope_doc_ids or None
        )
    except Exception as exc:
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"_Error: {type(exc).__name__}: {exc}_",
            "error": True,
        })
        return

    st.session_state.messages.append({
        "role": "assistant",
        "content": result.get("final_response", "_no response_"),
        "language": result.get("detected_language"),
        "intent": result.get("intent"),
        "sources": result.get("sources_used") or [],
    })


def render_message(msg: dict) -> None:
    role = msg["role"]
    avatar = "👤" if role == "user" else "🤖"
    with st.chat_message(role, avatar=avatar):
        st.markdown(msg["content"])
        if role == "assistant" and not msg.get("error"):
            _render_assistant_meta(msg)


def _render_assistant_meta(msg: dict) -> None:
    parts: list[str] = []
    if msg.get("language"):
        parts.append(render_tag(f"🌐 {msg['language'].upper()}", kind="info"))
    if msg.get("intent"):
        parts.append(render_tag(f"🎯 {msg['intent']}", kind="info"))
    sources = msg.get("sources") or []
    if sources:
        parts.append(render_tag(f"📚 {', '.join(sources)}", kind="success"))
    else:
        parts.append(render_tag("📚 no sources", kind="warn"))
    if parts:
        st.markdown(
            "<div style='margin-top:0.5rem;'>" + " ".join(parts) + "</div>",
            unsafe_allow_html=True,
        )


# ── Render ──────────────────────────────────────────────────────────


if not st.session_state.messages:
    render_empty_state()
else:
    for m in st.session_state.messages:
        render_message(m)


# Sticky input
user_input = st.chat_input("Ask about your customs documents or Uzbek law…")
if user_input:
    # Show the user message immediately, then run the agent
    with st.chat_message("user", avatar="👤"):
        st.markdown(user_input)
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Thinking…"):
            _submit(user_input)
        # The last appended message is the assistant's response
        last = st.session_state.messages[-1]
        st.markdown(last["content"])
        if not last.get("error"):
            _render_assistant_meta(last)