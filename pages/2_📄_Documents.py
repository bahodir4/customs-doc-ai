"""Documents page — upload customs files and view extracted data."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import streamlit as st

# Make the project root importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.components import (
    doc_type_badge,
    empty_state,
    format_timestamp,
    sidebar_brand,
    status_badge,
)
from app.document_export import to_excel_bytes, to_json_bytes
from app.services import (
    delete_document,
    get_document,
    list_documents,
    process_document,
)
from app.styles import inject_styles
from config import settings

# ── Page config ─────────────────────────────────────────────────────


st.set_page_config(
    page_title="Customs AI · Documents",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_styles()

with st.sidebar:
    sidebar_brand()
    st.markdown("---")
    st.markdown("**Supported formats**")
    st.caption("PDF (with text layer or scanned), JPG, PNG")
    st.markdown("---")
    st.markdown("**What happens on upload**")
    st.caption(
        "1. OCR (PDF text-layer fast-path, PaddleOCR fallback)\n\n"
        "2. Document classification\n\n"
        "3. Structured extraction into Pydantic schema\n\n"
        "4. Validation + Qdrant embedding for semantic search"
    )


# ── Constants ───────────────────────────────────────────────────────


UPLOADS_DIR: Path = settings.project_root / "data" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


# ── Header ──────────────────────────────────────────────────────────


st.title("📄 Documents")
st.caption(
    "Upload customs documents (invoices, AWBs, GTDs, CMRs, packing lists). "
    "Each file runs through OCR, classification, structured extraction, and is "
    "indexed for chat queries."
)


# ── Upload section ──────────────────────────────────────────────────


uploaded_files = st.file_uploader(
    "Drop files here or click to browse",
    type=["pdf", "jpg", "jpeg", "png"],
    accept_multiple_files=True,
    label_visibility="collapsed",
)

if uploaded_files:
    if st.button(f"Process {len(uploaded_files)} file(s)", type="primary"):
        progress_container = st.container()
        for i, f in enumerate(uploaded_files, start=1):
            with progress_container.status(
                f"[{i}/{len(uploaded_files)}] Processing **{f.name}**…",
                expanded=True,
            ) as status:
                # Persist the upload to data/uploads/ before invoking the pipeline.
                safe_name = f"{uuid.uuid4().hex[:8]}_{f.name}"
                disk_path = UPLOADS_DIR / safe_name
                disk_path.write_bytes(f.read())
                st.write(f"Saved to `{disk_path.name}`")
                st.write("Running OCR → classify → extract → validate → store…")
                try:
                    result = process_document(str(disk_path))
                except Exception as exc:
                    status.update(
                        label=f"× Failed: {f.name}", state="error", expanded=True
                    )
                    st.error(f"{type(exc).__name__}: {exc}")
                    continue

                if result.get("status") == "done":
                    status.update(
                        label=f"✓ Done: {f.name}", state="complete", expanded=False
                    )
                    st.write(
                        f"Type: **{result.get('doc_type')}** · "
                        f"OCR pages: **{result.get('ocr_pages')}** · "
                        f"OCR used: **{result.get('ocr_used')}** · "
                        f"Validation errors: **{len(result.get('validation_errors') or [])}**"
                    )
                else:
                    status.update(
                        label=f"× Error: {f.name}", state="error", expanded=True
                    )
                    st.error(result.get("error_message") or "Pipeline error.")

        st.success("Done. Scroll down to view processed documents.")
        st.cache_resource.clear()  # Refresh any cached doc lists
        st.rerun()


# ── Documents list ──────────────────────────────────────────────────


st.markdown("---")
st.subheader("Processed documents")

try:
    docs = list_documents(limit=200)
except Exception as exc:
    st.error(f"Could not load document list: {exc}")
    docs = []

if not docs:
    empty_state(
        icon="📥",
        title="No documents yet",
        description="Upload your first customs document above to see it here.",
    )
else:
    # ── Local renderers (defined first so they're available below) ──

    def _row(label: str, value) -> None:
        col_a, col_b = st.columns([1, 3])
        col_a.markdown(f"`{label}`")
        col_b.write("—" if value in (None, "") else value)

    def _render_fields(data: dict) -> None:
        """Render a flat 2-column field/value table for top-level fields."""
        for key, value in data.items():
            if isinstance(value, dict):
                st.markdown(f"**{key}**")
                with st.container():
                    for sub_key, sub_value in value.items():
                        _row(sub_key, sub_value)
            elif isinstance(value, list):
                st.markdown(f"**{key}** ({len(value)} items)")
                with st.container():
                    if value and isinstance(value[0], dict):
                        st.dataframe(value, use_container_width=True, hide_index=True)
                    else:
                        st.write(value)
            else:
                _row(key, value)

    # Quick filters
    col1, col2 = st.columns([3, 1])
    with col2:
        type_options = ["all"] + sorted({d["doc_type"] for d in docs if d.get("doc_type")})
        type_filter = st.selectbox("Filter by type", options=type_options, index=0)
    with col1:
        st.caption(f"{len(docs)} document(s) total")

    visible = docs if type_filter == "all" else [d for d in docs if d["doc_type"] == type_filter]

    for doc in visible:
        header = (
            f"{doc.get('file_name', '?')}  "
            f"{status_badge(doc.get('status', '?'))}  "
            f"{doc_type_badge(doc.get('doc_type', '?'))}  "
            f"<span style='color:#a1a1aa; font-size:0.85rem'>"
            f"· {format_timestamp(doc.get('created_at'))}</span>"
        )
        with st.expander(label=" ", expanded=False):
            st.markdown(header, unsafe_allow_html=True)
            st.markdown("---")

            # Action row
            action_col_1, action_col_2, action_col_3, _ = st.columns([1, 1, 1, 3])
            extracted = doc.get("extracted_data") or {}
            file_stem = Path(doc.get("file_name", "doc")).stem

            with action_col_1:
                st.download_button(
                    "📥 JSON",
                    data=to_json_bytes(extracted),
                    file_name=f"{file_stem}.json",
                    mime="application/json",
                    use_container_width=True,
                    key=f"json_{doc['id']}",
                )

            with action_col_2:
                try:
                    xlsx_bytes = to_excel_bytes(extracted)
                    st.download_button(
                        "📊 Excel",
                        data=xlsx_bytes,
                        file_name=f"{file_stem}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key=f"xlsx_{doc['id']}",
                    )
                except Exception as exc:
                    st.caption(f"_Excel error: {exc}_")

            with action_col_3:
                if st.button(
                    "🗑️ Delete",
                    use_container_width=True,
                    key=f"del_{doc['id']}",
                ):
                    try:
                        delete_document(doc["id"])
                        st.toast(f"Deleted {doc.get('file_name')}", icon="🗑️")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Delete failed: {exc}")

            # Validation errors
            errors = doc.get("validation_errors") or []
            if errors:
                st.warning(f"⚠ Validation errors ({len(errors)})")
                for e in errors:
                    st.markdown(f"- `{e}`")

            # Extracted data — fields + raw JSON tabs
            tab_fields, tab_json = st.tabs(["Fields", "Raw JSON"])
            with tab_fields:
                if extracted:
                    _render_fields(extracted)
                else:
                    st.caption("_no extracted data_")
            with tab_json:
                st.json(extracted, expanded=False)
