"""Documents page — upload customs files and view extracted data."""
from __future__ import annotations

import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.components import (
    doc_card_header,
    doc_type_badge,
    empty_state,
    format_timestamp,
    sidebar_brand,
    status_badge,
)
from app.document_export import to_csv_bytes, to_excel_bytes, to_json_bytes
from app.services import (
    delete_document_full,
    get_document,
    list_documents,
    stream_doc_pipeline,
)
from app.styles import inject_styles, render_section_header
from config import settings

# ── Page config ─────────────────────────────────────────────────────

st.set_page_config(
    page_title="Customs AI · Documents",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_styles()

# ── Sidebar ─────────────────────────────────────────────────────────

with st.sidebar:
    sidebar_brand()
    st.markdown("---")
    st.markdown(
        "<div style='font-size:0.75rem; font-weight:600; color:#64748b; "
        "text-transform:uppercase; letter-spacing:0.06em; margin-bottom:0.5rem;'>"
        "Supported formats</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='font-size:0.8125rem; color:#94a3b8; line-height:1.7;'>"
        "PDF &nbsp;·&nbsp; DOCX &nbsp;·&nbsp; JPG &nbsp;·&nbsp; PNG"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown(
        "<div style='font-size:0.75rem; font-weight:600; color:#64748b; "
        "text-transform:uppercase; letter-spacing:0.06em; margin-bottom:0.5rem;'>"
        "Processing pipeline</div>",
        unsafe_allow_html=True,
    )
    steps = [
        ("1", "OCR", "Text layer or PaddleOCR"),
        ("2", "Classify", "Detect document type"),
        ("3", "Extract", "Structured JSON via LLM"),
        ("4", "Index", "Qdrant embedding + store"),
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

UPLOADS_DIR: Path = settings.project_root / "data" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# ── Page header ──────────────────────────────────────────────────────

st.markdown(
    "<div class='page-header'>"
    "<h1>📄 Documents</h1>"
    "<p>Upload customs documents — invoices, AWBs, GTDs, CMRs, packing lists. "
    "Each file is OCR-processed, classified, and extracted into structured JSON.</p>"
    "</div>",
    unsafe_allow_html=True,
)

# ── Stat bar ─────────────────────────────────────────────────────────

try:
    all_docs = list_documents(limit=500)
except Exception:
    all_docs = []

if all_docs:
    type_counts = Counter(d.get("doc_type") or "unknown" for d in all_docs)
    status_counts = Counter(d.get("status") or "?" for d in all_docs)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total documents", len(all_docs))
    m2.metric("Processed", status_counts.get("done", 0))
    m3.metric("Errors", status_counts.get("error", 0))
    m4.metric("Doc types", len(type_counts))
    st.markdown("<div style='margin-bottom:0.5rem;'></div>", unsafe_allow_html=True)

# ── Upload section ───────────────────────────────────────────────────

st.markdown(
    render_section_header("Upload files"),
    unsafe_allow_html=True,
)

uploaded_files = st.file_uploader(
    "Drop files here or click to browse",
    type=["pdf", "docx", "jpg", "jpeg", "png"],
    accept_multiple_files=True,
    label_visibility="collapsed",
)

if uploaded_files:
    file_names = ", ".join(f.name for f in uploaded_files[:3])
    if len(uploaded_files) > 3:
        file_names += f" + {len(uploaded_files) - 3} more"
    col_btn, col_info = st.columns([2, 5])
    with col_btn:
        run = st.button(
            f"Process {len(uploaded_files)} file{'s' if len(uploaded_files) > 1 else ''}",
            type="primary",
            use_container_width=True,
        )
    with col_info:
        st.markdown(
            f"<div style='padding-top:0.55rem; font-size:0.875rem; color:var(--c-text-muted);'>"
            f"{file_names}</div>",
            unsafe_allow_html=True,
        )

    if run:
        _STAGE_SEQ = ["load", "ocr", "classify", "extract", "store"]
        _RUNNING_LABEL = {
            "load":     "📂 Loading file",
            "ocr":      "🔍 Extracting text (OCR)",
            "classify": "🏷️  Classifying document type",
            "extract":  "🧠 Extracting structured data",
            "store":    "💾 Storing in database + index",
        }
        _DONE_LABEL = {
            "load":     "📂 File loaded",
            "ocr":      "🔍 OCR complete",
            "classify": "🏷️  Classified",
            "extract":  "🧠 Data extracted",
            "store":    "💾 Stored",
        }

        def _stage_detail(stage: str, out: dict) -> str:
            if stage == "ocr":
                return f" — {out.get('ocr_pages', '?')} page(s) via {out.get('ocr_used', '?')}"
            if stage == "classify":
                return f" — **{out.get('doc_type', '?')}**"
            if stage == "extract":
                n = len(out.get("extracted_data") or {})
                return f" — {n} field(s)"
            if stage == "store":
                doc_id = str(out.get("doc_id") or "")[:8]
                return f" — id `{doc_id}…`" if doc_id else ""
            return ""

        for i, f in enumerate(uploaded_files, start=1):
            with st.status(
                f"[{i}/{len(uploaded_files)}] **{f.name}**",
                expanded=True,
            ) as status:
                safe_name = f"{uuid.uuid4().hex[:8]}_{f.name}"
                disk_path = UPLOADS_DIR / safe_name
                disk_path.write_bytes(f.read())

                st.write(f"◌ {_RUNNING_LABEL['load']}…")
                final: dict[str, Any] = {}
                try:
                    for stage, out in stream_doc_pipeline(str(disk_path)):
                        final.update(out)
                        if out.get("status") == "error":
                            st.write(
                                f"✕ {_DONE_LABEL.get(stage, stage)}"
                                f" — {out.get('error_message', 'error')}"
                            )
                            break
                        st.write(f"✓ {_DONE_LABEL.get(stage, stage)}{_stage_detail(stage, out)}")
                        idx = _STAGE_SEQ.index(stage) if stage in _STAGE_SEQ else -1
                        if idx + 1 < len(_STAGE_SEQ):
                            st.write(f"◌ {_RUNNING_LABEL[_STAGE_SEQ[idx + 1]]}…")
                except Exception as exc:
                    status.update(label=f"✕ Failed: {f.name}", state="error", expanded=True)
                    st.error(f"{type(exc).__name__}: {exc}")
                    continue

                if final.get("status") == "done":
                    status.update(label=f"✓ Done: {f.name}", state="complete", expanded=False)
                else:
                    err = final.get("error_message") or "Pipeline error."
                    status.update(label=f"✕ Error: {f.name}", state="error", expanded=True)
                    st.error(err)

        st.success("All files processed. See the list below.")
        st.cache_resource.clear()
        st.rerun()

# ── Document list ─────────────────────────────────────────────────────

docs = all_docs  # already loaded above

if not docs:
    empty_state(
        icon="📥",
        title="No documents yet",
        description="Upload your first customs document above to see it here.",
    )
else:
    # ── Field/value renderers ────────────────────────────────────────

    def _row(label: str, value) -> None:
        col_a, col_b = st.columns([1, 3])
        col_a.markdown(
            f"<span style='font-size:0.8rem; font-weight:500; color:var(--c-text-muted);'>{label}</span>",
            unsafe_allow_html=True,
        )
        col_b.write("—" if value in (None, "") else value)

    def _render_fields(data: dict) -> None:
        for key, value in data.items():
            if isinstance(value, dict):
                st.markdown(
                    f"<div style='font-size:0.875rem; font-weight:600; color:var(--c-text); "
                    f"margin: 0.875rem 0 0.375rem;'>{key}</div>",
                    unsafe_allow_html=True,
                )
                for sub_key, sub_value in value.items():
                    _row(sub_key, sub_value)
            elif isinstance(value, list):
                st.markdown(
                    f"<div style='font-size:0.875rem; font-weight:600; color:var(--c-text); "
                    f"margin: 0.875rem 0 0.375rem;'>{key} "
                    f"<span style='font-size:0.75rem; font-weight:500; color:var(--c-text-muted); "
                    f"background:var(--c-surface); border-radius:99px; padding:0.1rem 0.5rem; "
                    f"border:1px solid var(--c-border);'>{len(value)}</span></div>",
                    unsafe_allow_html=True,
                )
                if value and isinstance(value[0], dict):
                    flat_rows = [
                        {
                            k: (", ".join(map(str, v)) if isinstance(v, list)
                                else str(v) if isinstance(v, dict)
                                else v)
                            for k, v in row.items()
                        }
                        for row in value
                    ]
                    st.dataframe(flat_rows, use_container_width=True, hide_index=True)
                else:
                    st.write(value)
            else:
                _row(key, value)

    # ── Filters ──────────────────────────────────────────────────────

    filter_col, count_col = st.columns([3, 2])
    with filter_col:
        type_options = ["All types"] + sorted({d["doc_type"] for d in docs if d.get("doc_type")})
        type_filter = st.selectbox(
            "Filter by type",
            options=type_options,
            index=0,
            label_visibility="collapsed",
        )
    with count_col:
        st.markdown(
            f"<div style='padding-top:0.55rem; font-size:0.875rem; color:var(--c-text-muted); text-align:right;'>"
            f"{len(docs)} document{'s' if len(docs) != 1 else ''}</div>",
            unsafe_allow_html=True,
        )

    visible = docs if type_filter == "All types" else [d for d in docs if d["doc_type"] == type_filter]

    st.markdown(
        render_section_header("Processed documents", len(visible)),
        unsafe_allow_html=True,
    )

    for doc in visible:
        header_html = doc_card_header(doc)
        file_name = doc.get("file_name") or "Untitled"
        doc_type = doc.get("doc_type") or ""
        # Strip any leading uuid prefix (e.g. "a1b2c3d4_invoice.pdf" → "invoice.pdf")
        display_name = file_name.split("_", 1)[1] if "_" in file_name and len(file_name.split("_")[0]) == 8 else file_name
        tab_label = f"{display_name}  ·  {doc_type}" if doc_type else display_name
        with st.expander(label=tab_label, expanded=False):
            st.markdown(header_html, unsafe_allow_html=True)

            # ── Action toolbar ────────────────────────────────────────
            st.markdown(
                "<div style='height:0.75rem;'></div>",
                unsafe_allow_html=True,
            )
            extracted = doc.get("extracted_data") or {}
            file_stem = Path(doc.get("file_name", "doc")).stem

            a1, a2, a3, a4, _spacer = st.columns([1, 1, 1, 1, 3])

            with a1:
                st.download_button(
                    "⬇ JSON",
                    data=to_json_bytes(extracted),
                    file_name=f"{file_stem}.json",
                    mime="application/json",
                    use_container_width=True,
                    key=f"json_{doc['id']}",
                )
            with a2:
                try:
                    st.download_button(
                        "⬇ Excel",
                        data=to_excel_bytes(extracted),
                        file_name=f"{file_stem}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key=f"xlsx_{doc['id']}",
                    )
                except Exception as exc:
                    st.caption(f"_Excel: {exc}_")
            with a3:
                try:
                    st.download_button(
                        "⬇ CSV",
                        data=to_csv_bytes(extracted),
                        file_name=f"{file_stem}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key=f"csv_{doc['id']}",
                    )
                except Exception as exc:
                    st.caption(f"_CSV: {exc}_")
            with a4:
                if st.button(
                    "Delete",
                    use_container_width=True,
                    key=f"del_{doc['id']}",
                    type="secondary",
                ):
                    try:
                        delete_document_full(doc["id"])
                        st.toast(f"Deleted {doc.get('file_name')}", icon="🗑️")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Delete failed: {exc}")

            # ── Validation errors ─────────────────────────────────────
            errors = doc.get("validation_errors") or []
            if errors:
                st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
                st.warning(f"⚠ {len(errors)} validation error{'s' if len(errors) != 1 else ''}")
                for e in errors:
                    st.markdown(f"- `{e}`")

            # ── Data tabs ─────────────────────────────────────────────
            tab_fields, tab_json = st.tabs(["Fields", "Raw JSON"])
            with tab_fields:
                if extracted:
                    _render_fields(extracted)
                else:
                    st.caption("_No extracted data_")
            with tab_json:
                st.json(extracted, expanded=False)
