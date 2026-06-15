"""Knowledge Base page — ingest customs-law sources into the lex_uz collection."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.async_runner import run_async
from app.components import empty_state, sidebar_brand
from app.services import (
    delete_lex_source,
    get_lex_ingestion_service,
    get_services,
    list_lex_sources,
    stream_kb_ingest,
)
from app.styles import inject_styles, render_section_header
from config import settings

# ── Page config ──────────────────────────────────────────────────────

st.set_page_config(
    page_title="Customs AI · Knowledge Base",
    page_icon="📚",
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
        "How ingestion works</div>",
        unsafe_allow_html=True,
    )
    steps = [
        ("1", "Fetch / upload", "HTML → Markdown or direct .docx/.md"),
        ("2", "Chunk", "Split at # / ## headers"),
        ("3", "Embed", "BGE-M3, batches of 32"),
        ("4", "Store", "lex_uz Qdrant collection"),
        ("5", "Retrieve", "Chat agent uses as RAG context"),
    ]
    for num, label, desc in steps:
        st.markdown(
            f"<div style='display:flex; gap:0.625rem; margin-bottom:0.5rem; align-items:flex-start;'>"
            f"<div style='width:18px; height:18px; border-radius:50%; background:rgba(99,102,241,0.18); "
            f"color:#818cf8; font-size:0.6875rem; font-weight:700; display:flex; align-items:center; "
            f"justify-content:center; flex-shrink:0; margin-top:1px;'>{num}</div>"
            f"<div><div style='font-size:0.8125rem; font-weight:600; color:#e2e8f0; line-height:1.3;'>"
            f"{label}</div><div style='font-size:0.75rem; color:#64748b; line-height:1.4;'>{desc}</div></div>"
            f"</div>",
            unsafe_allow_html=True,
        )

# ── Constants ────────────────────────────────────────────────────────

ORIGINALS_DIR: Path = settings.project_root / "docs" / "lex_uz" / "originals"
MARKDOWN_DIR: Path = settings.project_root / "docs" / "lex_uz" / "markdown"
CONVERTED_DIR: Path = settings.project_root / "docs" / "lex_uz" / "converted"
ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)
CONVERTED_DIR.mkdir(parents=True, exist_ok=True)

# ── Page header ──────────────────────────────────────────────────────

st.markdown(
    "<div class='page-header'>"
    "<h1>📚 Knowledge Base</h1>"
    "<p>Ingest Uzbek customs law and regulations into the semantic search collection. "
    "Once stored, the chat agent automatically uses it as RAG context for regulation questions.</p>"
    "</div>",
    unsafe_allow_html=True,
)

# ── Collection stats ──────────────────────────────────────────────────

def _collection_stats() -> dict:
    try:
        svc = get_services()
        info = run_async(svc.vector._client.get_collection(settings.qdrant.lex_collection))
        return {"count": info.points_count or 0, "status": info.status}
    except Exception as exc:
        return {"error": str(exc)}

stats = _collection_stats()
try:
    lex_sources = list_lex_sources()
except Exception:
    lex_sources = []

m1, m2, m3 = st.columns(3)
if "error" in stats:
    m1.metric("Chunks in lex_uz", "—")
    m2.metric("Sources", "—")
    m3.error(stats["error"])
else:
    m1.metric("Chunks stored", f"{stats['count']:,}")
    m2.metric("Sources ingested", len(lex_sources))
    status_str = str(stats.get("status", "?"))
    m3.metric("Collection status", status_str)

# ── Ingestion: single URL or file ────────────────────────────────────

st.markdown(render_section_header("Add a source"), unsafe_allow_html=True)

tab_url, tab_file = st.tabs(["🔗  URL", "📁  Upload file"])

def _run_kb_ingest_ui(source, status_label: str) -> None:
    """Run KB ingestion with real-time stage updates inside an st.status() block."""
    with st.status(f"{status_label}…", expanded=True) as status:
        try:
            st.write("◌ 🔄 Fetching / loading file…")
            final: dict = {}
            for stage, data in stream_kb_ingest(source):
                if stage == "converting":
                    pass  # already shown above
                elif stage == "converted":
                    chars = data.get("chars", 0)
                    st.write(f"✓ 🔄 Converted to markdown — {chars:,} chars")
                    st.write("◌ ✂️  Chunking at #/## headers…")
                elif stage == "chunking":
                    pass
                elif stage == "chunked":
                    st.write(f"✓ ✂️  {data.get('count', '?')} chunks created")
                    st.write("◌ 🔢 Embedding (BGE-M3, batch 32)…")
                elif stage == "embedding":
                    pass
                elif stage == "stored":
                    st.write(f"✓ 🔢 Embedded and stored — {data.get('chunks_written', '?')} chunks")
                elif stage == "done":
                    final = data
            n = final.get("chunks_written", "?")
            status.update(label=f"✓ Ingested {n} chunks", state="complete")
            st.toast("Ingestion complete", icon="✅")
        except Exception as exc:
            status.update(label=f"✕ Failed: {exc}", state="error")
            st.error(str(exc))


with tab_url:
    st.markdown(
        "<div style='font-size:0.875rem; color:var(--c-text-muted); margin-bottom:0.75rem;'>"
        "Enter a URL to a static HTML page. For JS-rendered sites (e.g. lex.uz), "
        "export the DOCX and use the <strong>Upload file</strong> tab instead.</div>",
        unsafe_allow_html=True,
    )
    url = st.text_input(
        "Source URL",
        placeholder="https://example.com/customs-code",
        label_visibility="collapsed",
    )
    if st.button("Ingest URL", type="primary", disabled=not url, key="ingest_url"):
        _run_kb_ingest_ui(url, f"Ingesting {url[:60]}{'…' if len(url) > 60 else ''}")

with tab_file:
    st.markdown(
        "<div style='font-size:0.875rem; color:var(--c-text-muted); margin-bottom:0.75rem;'>"
        "Upload a <code>.docx</code>, <code>.md</code>, or <code>.txt</code> file to ingest directly.</div>",
        unsafe_allow_html=True,
    )
    uploaded = st.file_uploader(
        "Upload file",
        type=["docx", "md", "markdown", "txt"],
        accept_multiple_files=False,
        key="kb_single_upload",
        label_visibility="collapsed",
    )
    if uploaded:
        if st.button("Ingest file", type="primary", key="ingest_single_file"):
            tmp_path = ORIGINALS_DIR / f"{uuid.uuid4().hex[:8]}_{uploaded.name}"
            tmp_path.write_bytes(uploaded.read())
            _run_kb_ingest_ui(tmp_path, f"Ingesting {uploaded.name}")
            tmp_path.unlink(missing_ok=True)

# ── Bulk workflow ─────────────────────────────────────────────────────

st.markdown(render_section_header("Bulk workflow"), unsafe_allow_html=True)
st.markdown(
    f"<div style='font-size:0.875rem; color:var(--c-text-muted); margin-bottom:0.875rem;'>"
    f"Drop multiple files into <code>{ORIGINALS_DIR.relative_to(settings.project_root)}</code> "
    f"and run the batch ingestion below.</div>",
    unsafe_allow_html=True,
)

available_in_originals = sorted(
    p for p in ORIGINALS_DIR.iterdir()
    if p.is_file() and p.suffix.lower() in {".docx", ".md", ".markdown", ".txt"}
) if ORIGINALS_DIR.exists() else []

if available_in_originals:
    st.markdown(
        f"<div style='font-size:0.875rem; font-weight:600; color:var(--c-text); margin-bottom:0.5rem;'>"
        f"{len(available_in_originals)} file(s) pending in originals folder</div>",
        unsafe_allow_html=True,
    )
    for p in available_in_originals:
        st.markdown(
            f"<div style='font-size:0.8125rem; color:var(--c-text-muted); "
            f"font-family:monospace; margin-bottom:0.2rem;'>"
            f"📄 {p.name} <span style='color:var(--c-text-subtle);'>({p.stat().st_size / 1024:.1f} KB)</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
    delete_on_success = st.checkbox(
        "Delete source files after successful ingestion",
        value=True,
        key="bulk_delete_flag",
    )

    if st.button("Run bulk ingestion", type="primary"):
        with st.status("Bulk ingesting…", expanded=True) as bulk_status:
            succeeded, failed, total_chunks = 0, 0, 0
            st.write(f"Discovered {len(available_in_originals)} source file(s).")
            for src in available_in_originals:
                st.write(f"**{src.name}**")
                chunks_this = 0
                try:
                    for stage, data in stream_kb_ingest(src):
                        if stage == "converted":
                            st.write(f"  ✓ 🔄 Markdown — {data.get('chars', 0):,} chars")
                        elif stage == "chunked":
                            st.write(f"  ✓ ✂️  {data.get('count', '?')} chunks")
                        elif stage == "stored":
                            st.write(f"  ✓ 🔢 {data.get('chunks_written', '?')} chunks stored")
                        elif stage == "done":
                            chunks_this = data.get("chunks_written", 0)
                    succeeded += 1
                    total_chunks += chunks_this
                    if delete_on_success:
                        src.unlink(missing_ok=True)
                        st.write(f"  ✓ 🗑 Source deleted")
                except Exception as exc:
                    failed += 1
                    st.write(f"  ✕ {exc}")
            label = (
                f"✓ {succeeded} ok · {total_chunks} chunks"
                if failed == 0
                else f"⚠ {succeeded} ok, {failed} failed · {total_chunks} chunks"
            )
            bulk_status.update(label=label, state="complete" if failed == 0 else "error")
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

# ── Converted markdown backups ────────────────────────────────────────

converted_files = sorted(
    CONVERTED_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True
) if CONVERTED_DIR.exists() else []

st.markdown(
    render_section_header("Converted markdown backups", len(converted_files) if converted_files else None),
    unsafe_allow_html=True,
)
st.markdown(
    f"<div style='font-size:0.875rem; color:var(--c-text-muted); margin-bottom:0.875rem;'>"
    f"Every ingestion saves a copy of the converted markdown to "
    f"<code>{CONVERTED_DIR.relative_to(settings.project_root)}</code> "
    f"so you can inspect exactly what was sent to the chunker.</div>",
    unsafe_allow_html=True,
)

if not converted_files:
    st.markdown(
        "<div style='font-size:0.875rem; color:var(--c-text-muted); padding:0.5rem 0;'>"
        "No backups yet — they appear here after the first ingestion.</div>",
        unsafe_allow_html=True,
    )
else:
    for md_file in converted_files:
        stat = md_file.stat()
        size_kb = stat.st_size / 1024
        from datetime import datetime
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        col_name, col_size, col_time, col_btn = st.columns([5, 1, 2, 1])
        col_name.markdown(
            f"<div style='padding-top:0.45rem; font-size:0.8375rem; font-weight:500; "
            f"font-family:monospace; color:var(--c-text); overflow:hidden; "
            f"text-overflow:ellipsis; white-space:nowrap;'>{md_file.name}</div>",
            unsafe_allow_html=True,
        )
        col_size.markdown(
            f"<div style='padding-top:0.45rem; font-size:0.8125rem; color:var(--c-text-muted);'>"
            f"{size_kb:.1f} KB</div>",
            unsafe_allow_html=True,
        )
        col_time.markdown(
            f"<div style='padding-top:0.45rem; font-size:0.8125rem; color:var(--c-text-subtle);'>"
            f"{mtime}</div>",
            unsafe_allow_html=True,
        )
        if col_btn.button("View", key=f"view_md_{md_file.name}", type="secondary"):
            with st.expander(f"📄 {md_file.name}", expanded=True):
                st.download_button(
                    "⬇ Download .md",
                    data=md_file.read_bytes(),
                    file_name=md_file.name,
                    mime="text/markdown",
                    key=f"dl_{md_file.name}",
                )
                st.code(md_file.read_text(encoding="utf-8"), language="markdown")

# ── Ingested sources ──────────────────────────────────────────────────

st.markdown(
    render_section_header("Ingested sources", len(lex_sources) if lex_sources else None),
    unsafe_allow_html=True,
)

if not lex_sources:
    st.markdown(
        "<div style='font-size:0.875rem; color:var(--c-text-muted); padding:1rem 0;'>"
        "No sources ingested yet.</div>",
        unsafe_allow_html=True,
    )
else:
    for src_info in lex_sources:
        src_name = src_info["source"]
        chunk_count = src_info["chunks"]
        col_name, col_count, col_btn = st.columns([6, 1, 1])
        col_name.markdown(
            f"<div style='padding-top:0.45rem; font-size:0.8375rem; font-weight:500; "
            f"font-family:monospace; color:var(--c-text); overflow:hidden; "
            f"text-overflow:ellipsis; white-space:nowrap;'>{src_name}</div>",
            unsafe_allow_html=True,
        )
        col_count.markdown(
            f"<div style='padding-top:0.45rem; font-size:0.8125rem; color:var(--c-text-muted); "
            f"font-weight:500;'>{chunk_count} chunks</div>",
            unsafe_allow_html=True,
        )
        if col_btn.button("Delete", key=f"del_lex_{src_name}", type="secondary"):
            try:
                delete_lex_source(src_name)
                st.toast(f"Deleted: {src_name}", icon="🗑️")
                st.rerun()
            except Exception as exc:
                st.error(f"Delete failed: {exc}")

# ── Danger zone ───────────────────────────────────────────────────────

st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
with st.expander("⚠ Danger zone — wipe entire collection"):
    st.markdown(
        "<div style='font-size:0.875rem; color:var(--c-text-muted); margin-bottom:0.75rem;'>"
        "This permanently removes all chunks from <code>lex_uz</code>. "
        "The next ingestion starts from zero.</div>",
        unsafe_allow_html=True,
    )
    confirm = st.text_input(
        "Type CLEAR to unlock:",
        placeholder="CLEAR",
        key="confirm_clear",
        label_visibility="visible",
    )
    disabled = confirm != "CLEAR"
    if st.button("Wipe lex_uz collection", disabled=disabled, type="secondary"):
        try:
            svc = get_services()
            collection = settings.qdrant.lex_collection
            run_async(svc.vector._client.delete_collection(collection))
            run_async(svc.vector.ensure_collections())
            st.success(f"Collection `{collection}` cleared and recreated.")
            st.rerun()
        except Exception as exc:
            st.error(f"Clear failed: {exc}")
