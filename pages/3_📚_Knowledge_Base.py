"""Knowledge Base page — ingest customs-law sources into the lex_uz collection."""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

import streamlit as st

# Make project root importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.async_runner import run_async
from app.components import empty_state, sidebar_brand
from app.services import (
    delete_lex_source,
    get_lex_ingestion_service,
    get_services,
    ingest_kb_source,
    list_lex_sources,
)
from app.styles import inject_styles, render_tag
from config import settings
from rag.bulk_ingest import BulkIngestWorkflow

# ── Page config ─────────────────────────────────────────────────────


st.set_page_config(
    page_title="Customs AI · Knowledge Base",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_styles()

with st.sidebar:
    sidebar_brand()
    st.markdown("---")
    st.markdown("**Workflow**")
    st.caption(
        "1. Upload .docx or .md (or paste a URL).\n\n"
        "2. Hierarchical chunker splits by `#/##/###` headers.\n\n"
        "3. BGE-M3 embeds each chunk (batched 32 at a time).\n\n"
        "4. Stored in the `lex_uz` Qdrant collection.\n\n"
        "5. Chat agent automatically uses it as context for RAG queries."
    )

# ── Constants ───────────────────────────────────────────────────────


ORIGINALS_DIR: Path = settings.project_root / "docs" / "lex_uz" / "originals"
MARKDOWN_DIR: Path = settings.project_root / "docs" / "lex_uz" / "markdown"
ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)


# ── Header ──────────────────────────────────────────────────────────


st.title("📚 Knowledge Base")
st.caption(
    "Ingest Uzbek customs law into the semantic search collection. "
    "Once ingested, the chat agent will use it as context for regulation questions."
)


# ── Collection stats ────────────────────────────────────────────────


def _collection_stats() -> dict:
    """Get current chunk count from Qdrant."""
    try:
        svc = get_services()
        info = run_async(
            svc.vector._client.get_collection(settings.qdrant.lex_collection)
        )
        return {
            "count": info.points_count or 0,
            "status": info.status,
        }
    except Exception as exc:
        return {"error": str(exc)}


stats = _collection_stats()
col1, col2, col3 = st.columns(3)
if "error" in stats:
    col1.metric("Chunks in lex_uz", "—")
    col2.metric("Status", "Error")
    col3.error(stats["error"])
else:
    col1.metric("Chunks in lex_uz", f"{stats['count']:,}")
    col2.metric("Status", str(stats["status"]))


# ── Ingestion: single URL or file ───────────────────────────────────


st.markdown("---")
st.subheader("Ingest a single source")

tab_url, tab_file = st.tabs(["URL", "Upload file"])

with tab_url:
    url = st.text_input(
        "Source URL",
        placeholder="https://example.com/customs_code (static HTML)",
        label_visibility="collapsed",
    )
    st.caption(
        "Static HTML works directly. JS-rendered pages (e.g. lex.uz) need "
        "the DOCX export — use the **Upload file** tab below."
    )
    if st.button("Ingest URL", type="primary", disabled=not url, key="ingest_url"):
        with st.status(f"Ingesting {url}…", expanded=True) as status:
            try:
                st.write("Fetching, converting to markdown…")
                result = ingest_kb_source(url)
                st.write(
                    f"Chunked + embedded: **{result.chunks_written}** chunks "
                    f"from **{result.raw_markdown_chars:,}** chars of markdown."
                )
                status.update(
                    label=f"✓ Ingested {result.chunks_written} chunks",
                    state="complete",
                )
                st.toast("Ingestion complete", icon="✅")
            except Exception as exc:
                status.update(label=f"× Failed: {exc}", state="error")
                st.error(str(exc))

with tab_file:
    uploaded = st.file_uploader(
        "Upload a .docx or .md file",
        type=["docx", "md", "markdown", "txt"],
        accept_multiple_files=False,
        key="kb_single_upload",
    )
    if uploaded:
        if st.button("Ingest file", type="primary", key="ingest_single_file"):
            tmp_path = ORIGINALS_DIR / f"{uuid.uuid4().hex[:8]}_{uploaded.name}"
            tmp_path.write_bytes(uploaded.read())
            with st.status(f"Ingesting {uploaded.name}…", expanded=True) as status:
                try:
                    st.write(f"Saved to `{tmp_path.name}`")
                    st.write("Converting to markdown, chunking, embedding (32-batch)…")
                    result = ingest_kb_source(tmp_path)
                    st.write(
                        f"Chunked + embedded: **{result.chunks_written}** chunks."
                    )
                    status.update(
                        label=f"✓ Ingested {result.chunks_written} chunks",
                        state="complete",
                    )
                    # Clean up the temp file on success
                    tmp_path.unlink(missing_ok=True)
                    st.toast("Ingestion complete", icon="✅")
                except Exception as exc:
                    status.update(label=f"× Failed: {exc}", state="error")
                    st.error(str(exc))


# ── Bulk workflow ───────────────────────────────────────────────────


st.markdown("---")
st.subheader("Bulk workflow")
st.caption(
    f"Drop multiple files into `{ORIGINALS_DIR.relative_to(settings.project_root)}`. "
    "Each is converted to markdown, ingested, then both copies are deleted on success."
)

available_in_originals = sorted(
    p for p in ORIGINALS_DIR.iterdir()
    if p.is_file() and p.suffix.lower() in {".docx", ".md", ".markdown", ".txt"}
) if ORIGINALS_DIR.exists() else []

if available_in_originals:
    st.markdown(
        f"**Pending in originals folder: {len(available_in_originals)} file(s)**"
    )
    for p in available_in_originals:
        st.markdown(f"- `{p.name}` ({p.stat().st_size / 1024:.1f} KB)")

    delete_on_success = st.checkbox(
        "Delete files from both folders on successful ingest",
        value=True,
        key="bulk_delete_flag",
    )

    if st.button("Run bulk ingestion", type="primary"):
        ingest_service = get_lex_ingestion_service()
        workflow = BulkIngestWorkflow(
            originals_dir=ORIGINALS_DIR,
            markdown_dir=MARKDOWN_DIR,
            ingest_service=ingest_service,
            delete_after_success=delete_on_success,
        )

        with st.status("Bulk ingesting…", expanded=True) as status:
            sources = workflow.discover_sources()
            st.write(f"Discovered {len(sources)} source file(s).")

            succeeded = 0
            failed = 0
            total_chunks = 0
            for src in sources:
                st.write(f"→ {src.name}")
                result = run_async(workflow.process_one(src))
                if result.status == "ok":
                    succeeded += 1
                    total_chunks += result.chunks_written
                    st.write(
                        f"  ✓ {result.chunks_written} chunks "
                        f"({'deleted' if result.deleted else 'kept'})"
                    )
                else:
                    failed += 1
                    st.write(f"  × {result.error}")

            label = (
                f"✓ {succeeded} ok, {failed} failed · {total_chunks} chunks"
                if failed == 0
                else f"⚠ {succeeded} ok, {failed} failed"
            )
            status.update(
                label=label, state="complete" if failed == 0 else "error"
            )
        st.rerun()

else:
    empty_state(
        icon="📂",
        title="Originals folder is empty",
        description=(
            f"Drop .docx / .md files into "
            f"<code>{ORIGINALS_DIR.relative_to(settings.project_root)}</code> "
            f"then come back to run the bulk workflow."
        ),
    )


# ── Ingested sources ────────────────────────────────────────────────


st.markdown("---")
st.subheader("Ingested sources")
st.caption("All sources currently stored in the lex_uz vector collection.")

try:
    lex_sources = list_lex_sources()
except Exception as _exc:
    lex_sources = []
    st.warning(f"Could not load sources: {_exc}")

if not lex_sources:
    st.info("No sources ingested yet.")
else:
    for src_info in lex_sources:
        src_name = src_info["source"]
        chunk_count = src_info["chunks"]
        col_name, col_count, col_btn = st.columns([5, 1, 1])
        col_name.markdown(f"`{src_name}`")
        col_count.markdown(f"**{chunk_count}** chunks")
        if col_btn.button("Delete", key=f"del_lex_{src_name}", type="secondary"):
            try:
                delete_lex_source(src_name)
                st.toast(f"Deleted: {src_name}", icon="🗑️")
                st.rerun()
            except Exception as exc:
                st.error(f"Delete failed: {exc}")


# ── Danger zone ─────────────────────────────────────────────────────


st.markdown("---")
with st.expander("⚠ Danger zone"):
    st.caption("Wipe the entire lex_uz collection. The next ingestion starts from zero.")
    confirm = st.text_input(
        "Type **CLEAR** to enable the button:",
        key="confirm_clear",
    )
    disabled = confirm != "CLEAR"
    if st.button("Clear lex_uz collection", disabled=disabled, type="secondary"):
        try:
            svc = get_services()
            collection = settings.qdrant.lex_collection
            run_async(svc.vector._client.delete_collection(collection))
            run_async(svc.vector.ensure_collections())
            st.success(f"Collection `{collection}` cleared and recreated.")
            st.rerun()
        except Exception as exc:
            st.error(f"Clear failed: {exc}")
