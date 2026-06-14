"""Custom CSS injection — Streamlit page → polished AI-chat UI."""
from __future__ import annotations

import streamlit as st

_CSS = """
<style>
/* ─── Variables ────────────────────────────────────────────────── */
:root {
    --c-bg: #ffffff;
    --c-surface: #fafafa;
    --c-surface-2: #f4f4f5;
    --c-border: #e4e4e7;
    --c-border-strong: #d4d4d8;
    --c-text: #18181b;
    --c-text-muted: #71717a;
    --c-text-subtle: #a1a1aa;
    --c-accent: #2563eb;
    --c-accent-hover: #1d4ed8;
    --c-success: #10b981;
    --c-error: #ef4444;
    --c-warning: #f59e0b;
}

/* ─── Global typography ────────────────────────────────────────── */
.stApp {
    font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI",
                 Roboto, "Helvetica Neue", sans-serif;
    background: var(--c-bg);
    color: var(--c-text);
}

.stApp h1, .stApp h2, .stApp h3, .stApp h4 {
    font-weight: 600;
    letter-spacing: -0.01em;
}

/* ─── Layout ──────────────────────────────────────────────────── */
.block-container {
    padding-top: 2.5rem !important;
    padding-bottom: 6rem !important;
    max-width: 860px !important;
}

/* Hide Streamlit chrome */
#MainMenu, header[data-testid="stHeader"], footer {visibility: hidden;}
.stDeployButton {display: none !important;}

/* ─── Sidebar ─────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: var(--c-surface);
    border-right: 1px solid var(--c-border);
}

section[data-testid="stSidebar"] .block-container {
    padding-top: 2rem !important;
}

section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: var(--c-text);
    font-weight: 600;
}

section[data-testid="stSidebar"] hr {
    border-color: var(--c-border);
    margin: 1.5rem 0;
}

/* Sidebar nav links */
section[data-testid="stSidebarNav"] {
    background: transparent;
}

section[data-testid="stSidebarNav"] a {
    border-radius: 8px;
    padding: 0.5rem 0.75rem;
    transition: background 0.15s ease;
}

section[data-testid="stSidebarNav"] a:hover {
    background: var(--c-surface-2);
}

/* ─── Chat messages ───────────────────────────────────────────── */
[data-testid="stChatMessage"] {
    padding: 1.25rem 1.5rem !important;
    margin-bottom: 0.75rem !important;
    border-radius: 12px !important;
    border: 1px solid var(--c-border) !important;
    background: var(--c-bg) !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02);
}

/* Slightly different shade for user vs assistant — Streamlit doesn't
   expose role classes directly, so we lean on the avatar order. */
[data-testid="stChatMessage"]:has([data-testid*="user"]) {
    background: var(--c-surface) !important;
}

[data-testid="stChatMessage"] p {
    line-height: 1.6;
    margin-bottom: 0.5rem;
}

[data-testid="stChatMessageAvatar"] {
    width: 30px !important;
    height: 30px !important;
    border-radius: 8px !important;
}

/* ─── Chat input ──────────────────────────────────────────────── */
[data-testid="stChatInput"] {
    border-radius: 16px !important;
    background: var(--c-bg) !important;
    border: 1px solid var(--c-border-strong) !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04) !important;
    padding: 0.25rem !important;
}

[data-testid="stChatInput"]:focus-within {
    border-color: var(--c-accent) !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1) !important;
}

[data-testid="stChatInput"] textarea {
    font-size: 1rem !important;
    line-height: 1.5 !important;
    padding: 0.75rem 1rem !important;
}

[data-testid="stChatInput"] button {
    border-radius: 10px !important;
}

/* ─── Buttons ─────────────────────────────────────────────────── */
.stButton button, .stDownloadButton button {
    border-radius: 8px !important;
    border: 1px solid var(--c-border-strong) !important;
    background: var(--c-bg) !important;
    color: var(--c-text) !important;
    font-weight: 500 !important;
    padding: 0.5rem 1rem !important;
    transition: all 0.15s ease !important;
    box-shadow: none !important;
}

.stButton button:hover, .stDownloadButton button:hover {
    background: var(--c-surface) !important;
    border-color: var(--c-text-muted) !important;
    transform: translateY(-1px);
}

.stButton button[kind="primary"] {
    background: var(--c-text) !important;
    color: white !important;
    border-color: var(--c-text) !important;
}

.stButton button[kind="primary"]:hover {
    background: #27272a !important;
    border-color: #27272a !important;
}

/* ─── Inputs ──────────────────────────────────────────────────── */
.stTextInput input, .stTextArea textarea, .stSelectbox > div > div {
    border-radius: 8px !important;
    border: 1px solid var(--c-border-strong) !important;
    background: var(--c-bg) !important;
}

.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: var(--c-accent) !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1) !important;
}

/* ─── File uploader ───────────────────────────────────────────── */
[data-testid="stFileUploader"] section {
    border-radius: 12px !important;
    border: 2px dashed var(--c-border-strong) !important;
    background: var(--c-surface) !important;
    padding: 2.5rem 1.5rem !important;
    transition: all 0.15s ease;
}

[data-testid="stFileUploader"] section:hover {
    border-color: var(--c-accent) !important;
    background: var(--c-surface-2) !important;
}

[data-testid="stFileUploader"] button {
    border-radius: 8px !important;
}

/* ─── Expanders ───────────────────────────────────────────────── */
.streamlit-expanderHeader, [data-testid="stExpander"] summary {
    border-radius: 10px !important;
    padding: 0.75rem 1rem !important;
    font-weight: 500 !important;
    background: var(--c-surface) !important;
    border: 1px solid var(--c-border) !important;
}

[data-testid="stExpander"] {
    border: none !important;
    border-radius: 10px !important;
    margin-bottom: 0.5rem;
}

[data-testid="stExpander"] details {
    border: 1px solid var(--c-border);
    border-radius: 10px;
    overflow: hidden;
}

[data-testid="stExpander"] details[open] summary {
    border-bottom: 1px solid var(--c-border) !important;
    border-radius: 10px 10px 0 0 !important;
}

/* ─── Tags / badges (custom) ──────────────────────────────────── */
.tag {
    display: inline-block;
    padding: 0.2rem 0.65rem;
    font-size: 0.75rem;
    font-weight: 500;
    border-radius: 999px;
    background: var(--c-surface-2);
    color: var(--c-text-muted);
    margin-right: 0.4rem;
}

.tag-success { background: #ecfdf5; color: #059669; }
.tag-error   { background: #fef2f2; color: #dc2626; }
.tag-info    { background: #eff6ff; color: #2563eb; }
.tag-warn    { background: #fffbeb; color: #d97706; }

/* Status pill with dot */
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.25rem 0.65rem;
    font-size: 0.8rem;
    border-radius: 999px;
    background: var(--c-surface-2);
}

.status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--c-text-subtle);
}

.status-dot.ok    { background: var(--c-success); box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.15); }
.status-dot.err   { background: var(--c-error); box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.15); }

/* ─── Empty state ─────────────────────────────────────────────── */
.empty-state {
    text-align: center;
    padding: 4rem 1rem;
    color: var(--c-text-muted);
}

.empty-state h2 {
    font-size: 1.5rem;
    margin-bottom: 0.5rem;
    color: var(--c-text);
}

.empty-state p {
    font-size: 1rem;
    margin-bottom: 2rem;
}

/* ─── Code & JSON ─────────────────────────────────────────────── */
.stMarkdown code, pre {
    border-radius: 6px !important;
    font-family: "SF Mono", Monaco, "Cascadia Code", monospace !important;
}

[data-testid="stJson"] {
    background: var(--c-surface) !important;
    border: 1px solid var(--c-border) !important;
    border-radius: 8px !important;
    padding: 0.75rem !important;
}

/* ─── Dividers ────────────────────────────────────────────────── */
hr {
    border: none !important;
    height: 1px !important;
    background: var(--c-border) !important;
    margin: 2rem 0 !important;
}

/* ─── Scrollbar ───────────────────────────────────────────────── */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

::-webkit-scrollbar-track {
    background: transparent;
}

::-webkit-scrollbar-thumb {
    background: var(--c-border-strong);
    border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--c-text-subtle);
}

/* ─── Hide stray elements ─────────────────────────────────────── */
.stApp [data-testid="stToolbar"] {
    visibility: hidden;
}
</style>
"""


def inject_styles() -> None:
    """Inject the global stylesheet. Call once per page (top of script)."""
    st.markdown(_CSS, unsafe_allow_html=True)


def render_status_pill(label: str, ok: bool) -> str:
    """Return the HTML for an inline status pill (use with `unsafe_allow_html`)."""
    cls = "ok" if ok else "err"
    return (
        f'<div class="status-pill">'
        f'<span class="status-dot {cls}"></span>{label}'
        f'</div>'
    )


def render_tag(text: str, kind: str = "info") -> str:
    """Return the HTML for a colored tag pill."""
    return f'<span class="tag tag-{kind}">{text}</span>'
