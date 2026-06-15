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
from app.styles import inject_styles
from config import settings

st.set_page_config(
    page_title="Customs AI · Settings",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_styles()

with st.sidebar:
    sidebar_brand()

st.title("⚙️ Settings")

# ── Database ─────────────────────────────────────────────────────────

st.subheader("PostgreSQL")

try:
    db_ready = tables_exist()
except Exception as _e:
    db_ready = False
    st.error(f"Cannot reach PostgreSQL: {_e}")

if db_ready:
    st.success("✓ Database tables are ready.")

    try:
        doc_count = len(list_documents(limit=1000))
    except Exception:
        doc_count = "?"

    st.metric("Documents stored", doc_count)

    st.markdown("---")
    with st.expander("⚠ Danger zone — drop tables"):
        st.warning(
            "This **permanently deletes all documents** from PostgreSQL. "
            "Vector chunks in Qdrant are NOT removed (use the collection controls below)."
        )
        confirm = st.text_input("Type **DROP** to enable:", key="confirm_drop_db")
        if st.button("Drop all tables", disabled=confirm != "DROP", type="secondary"):
            try:
                drop_db()
                st.success("Tables dropped. Refresh the page to re-initialise.")
                st.rerun()
            except Exception as exc:
                st.error(f"Drop failed: {exc}")
else:
    st.warning("Database tables not found. Initialise them to start using the app.")
    if st.button("Initialize database", type="primary"):
        try:
            init_db()
            st.success("✓ Tables created successfully.")
            st.rerun()
        except Exception as exc:
            st.error(f"Init failed: {exc}")

# ── Qdrant collections ───────────────────────────────────────────────

st.markdown("---")
st.subheader("Qdrant vector collections")

try:
    svc = get_services()

    col_doc, col_lex = st.columns(2)

    # doc_chunks collection
    with col_doc:
        st.markdown("**doc_chunks** — uploaded documents")
        try:
            info = run_async(
                svc.vector._client.get_collection(settings.qdrant.doc_collection)
            )
            st.metric("Chunks", f"{info.points_count or 0:,}")
            st.caption(f"Status: {info.status}")

            # Per-document chunk counts
            chunk_counts = list_doc_chunk_counts()
            if chunk_counts:
                docs = {d["id"]: d["file_name"] for d in list_documents(limit=500)}
                rows = [
                    {
                        "Document": docs.get(doc_id, doc_id),
                        "Chunks": cnt,
                        "doc_id": doc_id,
                    }
                    for doc_id, cnt in sorted(
                        chunk_counts.items(), key=lambda x: -x[1]
                    )
                ]
                st.dataframe(
                    [{"Document": r["Document"], "Chunks": r["Chunks"]} for r in rows],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("No chunks yet.")

            with st.expander("⚠ Clear doc_chunks"):
                if st.button("Wipe doc_chunks collection", type="secondary", key="wipe_doc"):
                    run_async(svc.vector._client.delete_collection(settings.qdrant.doc_collection))
                    run_async(svc.vector.ensure_collections())
                    st.success("doc_chunks cleared and recreated.")
                    st.rerun()
        except Exception as exc:
            st.warning(f"Cannot read doc_chunks: {exc}")

    # lex_uz collection
    with col_lex:
        st.markdown("**lex_uz** — knowledge base")
        try:
            info2 = run_async(
                svc.vector._client.get_collection(settings.qdrant.lex_collection)
            )
            st.metric("Chunks", f"{info2.points_count or 0:,}")
            st.caption(f"Status: {info2.status}")

            with st.expander("⚠ Clear lex_uz"):
                if st.button("Wipe lex_uz collection", type="secondary", key="wipe_lex"):
                    run_async(svc.vector._client.delete_collection(settings.qdrant.lex_collection))
                    run_async(svc.vector.ensure_collections())
                    st.success("lex_uz cleared and recreated.")
                    st.rerun()
        except Exception as exc:
            st.warning(f"Cannot read lex_uz: {exc}")

except Exception as exc:
    st.error(f"Cannot reach Qdrant: {exc}")

# ── Config summary ───────────────────────────────────────────────────

st.markdown("---")
st.subheader("Active configuration")

cfg_col1, cfg_col2 = st.columns(2)
with cfg_col1:
    st.markdown("**LLM**")
    st.code(
        f"Provider:  {settings.llm_provider}\n"
        f"Model:     "
        f"{settings.openai.chat_model if settings.llm_provider == 'openai' else settings.ollama.chat_model}\n"
        f"Embed:     {settings.ollama.embed_model}",
        language="text",
    )
with cfg_col2:
    st.markdown("**Infrastructure**")
    st.code(
        f"Ollama:    {settings.ollama.base_url}\n"
        f"Qdrant:    {settings.qdrant.host}:{settings.qdrant.port}\n"
        f"Postgres:  {settings.postgres.host}:{settings.postgres.port}/{settings.postgres.db}",
        language="text",
    )
