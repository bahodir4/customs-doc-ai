"""Settings page — database management and system status."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.async_runner import run_async
from app.components import sidebar_brand
from app.services import (
    drop_db,
    get_services,
    init_db,
    list_doc_chunk_counts,
    list_documents,
    tables_exist,
)
from app.styles import inject_styles, render_section_header
from config import settings

st.set_page_config(
    page_title="Customs AI · Settings",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_styles()

# ── Sidebar ──────────────────────────────────────────────────────────

with st.sidebar:
    sidebar_brand()
    st.markdown("---")
    st.markdown(
        "<div style='font-size:0.75rem; font-weight:600; color:#64748b; "
        "text-transform:uppercase; letter-spacing:0.06em; margin-bottom:0.5rem;'>"
        "Infrastructure</div>",
        unsafe_allow_html=True,
    )
    infra_items = [
        ("PostgreSQL", f"{settings.postgres.host}:{settings.postgres.port}/{settings.postgres.db}"),
        ("Qdrant", f"{settings.qdrant.host}:{settings.qdrant.port}"),
        ("Ollama", settings.ollama.base_url),
    ]
    for name, addr in infra_items:
        st.markdown(
            f"<div style='margin-bottom:0.375rem;'>"
            f"<div style='font-size:0.75rem; color:#64748b; font-weight:600;'>{name}</div>"
            f"<div style='font-size:0.75rem; color:#94a3b8; font-family:monospace;'>{addr}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

# ── Page header ───────────────────────────────────────────────────────

st.markdown(
    "<div class='page-header'>"
    "<h1>⚙️ Settings</h1>"
    "<p>Manage database tables, vector collections, and view the active configuration.</p>"
    "</div>",
    unsafe_allow_html=True,
)

# ── PostgreSQL ─────────────────────────────────────────────────────────

st.markdown(render_section_header("PostgreSQL"), unsafe_allow_html=True)

try:
    db_ready = tables_exist()
except Exception as _e:
    db_ready = False
    st.error(f"Cannot reach PostgreSQL: {_e}")

if db_ready:
    try:
        doc_count = len(list_documents(limit=1000))
    except Exception:
        doc_count = "?"

    db_col1, db_col2, db_col3 = st.columns(3)
    db_col1.metric("Documents stored", doc_count)
    db_col2.metric("Status", "Ready")
    db_col3.metric("Host", f"{settings.postgres.host}:{settings.postgres.port}")

    st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
    with st.expander("⚠ Danger zone — drop all tables"):
        st.markdown(
            "<div style='font-size:0.875rem; color:var(--c-text-muted); margin-bottom:0.75rem;'>"
            "This permanently deletes all document records from PostgreSQL. "
            "Vector chunks in Qdrant are <em>not</em> removed automatically — "
            "use the collection controls below to clear those separately.</div>",
            unsafe_allow_html=True,
        )
        confirm = st.text_input(
            "Type DROP to unlock:",
            placeholder="DROP",
            key="confirm_drop_db",
        )
        if st.button("Drop all tables", disabled=confirm != "DROP", type="secondary"):
            try:
                drop_db()
                st.success("Tables dropped. Refresh to re-initialise.")
                st.rerun()
            except Exception as exc:
                st.error(f"Drop failed: {exc}")
else:
    st.markdown(
        "<div style='background:var(--c-warning-bg); border:1.5px solid #fcd34d; "
        "border-radius:var(--r-lg); padding:1.125rem 1.25rem; "
        "font-size:0.9rem; color:var(--c-warning-text); margin-bottom:1rem;'>"
        "⚠ Database tables not found. Click <strong>Initialize</strong> to create them "
        "and start using the app.</div>",
        unsafe_allow_html=True,
    )
    if st.button("Initialize database", type="primary"):
        try:
            init_db()
            st.success("✓ Tables created successfully.")
            st.rerun()
        except Exception as exc:
            st.error(f"Init failed: {exc}")

# ── Qdrant collections ─────────────────────────────────────────────────

st.markdown(render_section_header("Qdrant vector collections"), unsafe_allow_html=True)

try:
    svc = get_services()
    col_doc, col_lex = st.columns(2)

    # ── doc_chunks ────────────────────────────────────────────────────
    with col_doc:
        st.markdown(
            "<div style='font-size:0.8125rem; font-weight:700; color:var(--c-text); "
            "text-transform:uppercase; letter-spacing:0.05em; margin-bottom:0.625rem;'>"
            "doc_chunks</div>"
            "<div style='font-size:0.8125rem; color:var(--c-text-muted); margin-bottom:0.75rem;'>"
            "Uploaded document embeddings</div>",
            unsafe_allow_html=True,
        )
        try:
            info = run_async(svc.vector._client.get_collection(settings.qdrant.doc_collection))
            d1, d2 = st.columns(2)
            d1.metric("Chunks", f"{info.points_count or 0:,}")
            d2.metric("Status", str(info.status))

            chunk_counts = list_doc_chunk_counts()
            if chunk_counts:
                docs = {d["id"]: d["file_name"] for d in list_documents(limit=500)}
                rows = [
                    {"Document": docs.get(doc_id, doc_id)[:40], "Chunks": cnt}
                    for doc_id, cnt in sorted(chunk_counts.items(), key=lambda x: -x[1])
                ]
                st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
                st.dataframe(rows, use_container_width=True, hide_index=True)
            else:
                st.caption("No chunks indexed yet.")

            st.markdown("<div style='height:0.375rem;'></div>", unsafe_allow_html=True)
            with st.expander("⚠ Clear doc_chunks"):
                st.markdown(
                    "<div style='font-size:0.8125rem; color:var(--c-text-muted); margin-bottom:0.5rem;'>"
                    "Wipe and recreate the doc_chunks collection. "
                    "PostgreSQL records are kept.</div>",
                    unsafe_allow_html=True,
                )
                if st.button("Wipe doc_chunks", type="secondary", key="wipe_doc"):
                    run_async(svc.vector._client.delete_collection(settings.qdrant.doc_collection))
                    run_async(svc.vector.ensure_collections())
                    st.success("doc_chunks cleared and recreated.")
                    st.rerun()
        except Exception as exc:
            st.warning(f"Cannot read doc_chunks: {exc}")

    # ── lex_uz ────────────────────────────────────────────────────────
    with col_lex:
        st.markdown(
            "<div style='font-size:0.8125rem; font-weight:700; color:var(--c-text); "
            "text-transform:uppercase; letter-spacing:0.05em; margin-bottom:0.625rem;'>"
            "lex_uz</div>"
            "<div style='font-size:0.8125rem; color:var(--c-text-muted); margin-bottom:0.75rem;'>"
            "Knowledge base (customs law)</div>",
            unsafe_allow_html=True,
        )
        try:
            info2 = run_async(svc.vector._client.get_collection(settings.qdrant.lex_collection))
            l1, l2 = st.columns(2)
            l1.metric("Chunks", f"{info2.points_count or 0:,}")
            l2.metric("Status", str(info2.status))

            st.markdown("<div style='height:0.375rem;'></div>", unsafe_allow_html=True)
            with st.expander("⚠ Clear lex_uz"):
                st.markdown(
                    "<div style='font-size:0.8125rem; color:var(--c-text-muted); margin-bottom:0.5rem;'>"
                    "Wipe and recreate the lex_uz collection. "
                    "Re-ingest sources from the Knowledge Base page afterwards.</div>",
                    unsafe_allow_html=True,
                )
                if st.button("Wipe lex_uz", type="secondary", key="wipe_lex"):
                    run_async(svc.vector._client.delete_collection(settings.qdrant.lex_collection))
                    run_async(svc.vector.ensure_collections())
                    st.success("lex_uz cleared and recreated.")
                    st.rerun()
        except Exception as exc:
            st.warning(f"Cannot read lex_uz: {exc}")

except Exception as exc:
    st.error(f"Cannot reach Qdrant: {exc}")

# ── Active configuration ───────────────────────────────────────────────

st.markdown(render_section_header("Active configuration"), unsafe_allow_html=True)

model_str = (
    settings.openai.chat_model
    if settings.llm_provider == "openai"
    else settings.ollama.chat_model
)

cfg_col1, cfg_col2 = st.columns(2)

with cfg_col1:
    st.markdown(
        "<div style='font-size:0.8125rem; font-weight:600; color:var(--c-text-muted); "
        "text-transform:uppercase; letter-spacing:0.05em; margin-bottom:0.5rem;'>LLM</div>",
        unsafe_allow_html=True,
    )
    st.code(
        f"Provider : {settings.llm_provider}\n"
        f"Model    : {model_str}\n"
        f"Embed    : {settings.ollama.embed_model}",
        language="text",
    )

with cfg_col2:
    st.markdown(
        "<div style='font-size:0.8125rem; font-weight:600; color:var(--c-text-muted); "
        "text-transform:uppercase; letter-spacing:0.05em; margin-bottom:0.5rem;'>Infrastructure</div>",
        unsafe_allow_html=True,
    )
    st.code(
        f"Ollama   : {settings.ollama.base_url}\n"
        f"Qdrant   : {settings.qdrant.host}:{settings.qdrant.port}\n"
        f"Postgres : {settings.postgres.host}:{settings.postgres.port}/{settings.postgres.db}",
        language="text",
    )
