"""Custom CSS injection — professional SaaS-style design system."""
from __future__ import annotations

import streamlit as st

_CSS = """
<style>
/* ─── Design tokens ─────────────────────────────────────────────── */
:root {
    /* Sidebar (dark navy) */
    --sb-bg:          #0f172a;
    --sb-bg-hover:    rgba(99, 102, 241, 0.12);
    --sb-bg-active:   rgba(99, 102, 241, 0.18);
    --sb-text:        #94a3b8;
    --sb-text-strong: #f1f5f9;
    --sb-border:      rgba(255,255,255,0.07);
    --sb-accent:      #818cf8;

    /* Content area */
    --c-bg:           #f8fafc;
    --c-card:         #ffffff;
    --c-surface:      #f1f5f9;
    --c-surface-2:    #e8edf5;
    --c-border:       #e2e8f0;
    --c-border-strong:#cbd5e1;
    --c-text:         #0f172a;
    --c-text-muted:   #64748b;
    --c-text-subtle:  #94a3b8;

    /* Accent (indigo) */
    --c-accent:       #6366f1;
    --c-accent-hover: #4f46e5;
    --c-accent-light: #eef2ff;
    --c-accent-ring:  rgba(99, 102, 241, 0.2);

    /* Semantic */
    --c-success:      #10b981;
    --c-success-bg:   #ecfdf5;
    --c-success-text: #065f46;
    --c-error:        #ef4444;
    --c-error-bg:     #fef2f2;
    --c-error-text:   #991b1b;
    --c-warning:      #f59e0b;
    --c-warning-bg:   #fffbeb;
    --c-warning-text: #92400e;
    --c-info:         #3b82f6;
    --c-info-bg:      #eff6ff;
    --c-info-text:    #1e40af;

    /* Elevation */
    --shadow-xs: 0 1px 2px rgba(0,0,0,0.04);
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
    --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.06), 0 2px 4px -1px rgba(0,0,0,0.03);
    --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.06), 0 4px 6px -2px rgba(0,0,0,0.03);

    /* Shape */
    --r-sm: 6px;
    --r-md: 10px;
    --r-lg: 14px;
    --r-xl: 18px;
    --r-full: 9999px;
}

/* ─── Global ────────────────────────────────────────────────────── */
.stApp {
    font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI",
                 Roboto, sans-serif;
    background: var(--c-bg);
    color: var(--c-text);
    font-size: 0.9375rem;
}

.stApp h1 { font-size: 1.625rem; font-weight: 700; letter-spacing: -0.02em; color: var(--c-text); }
.stApp h2 { font-size: 1.25rem;  font-weight: 650; letter-spacing: -0.015em; color: var(--c-text); }
.stApp h3 { font-size: 1.05rem;  font-weight: 600; letter-spacing: -0.01em; color: var(--c-text); }

p, li { line-height: 1.65; }

/* ─── Chrome hiding ─────────────────────────────────────────────── */
#MainMenu, header[data-testid="stHeader"], footer,
.stDeployButton, [data-testid="stToolbar"] {
    display: none !important;
    visibility: hidden !important;
}

/* ─── Layout ────────────────────────────────────────────────────── */
.block-container {
    padding-top: 2rem !important;
    padding-bottom: 5rem !important;
    padding-left: 2.5rem !important;
    padding-right: 2.5rem !important;
    max-width: 1080px !important;
}

/* ─── Sidebar — dark ────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: var(--sb-bg) !important;
    border-right: 1px solid var(--sb-border) !important;
}

section[data-testid="stSidebar"] .block-container {
    padding-top: 1.5rem !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
}

section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] caption {
    color: var(--sb-text) !important;
}

section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] strong {
    color: var(--sb-text-strong) !important;
}

section[data-testid="stSidebar"] hr {
    border-color: var(--sb-border) !important;
    margin: 1rem 0 !important;
}

/* Sidebar nav */
section[data-testid="stSidebarNav"] {
    background: transparent !important;
    padding-top: 0.5rem;
}

section[data-testid="stSidebarNav"] a {
    color: var(--sb-text) !important;
    border-radius: var(--r-md) !important;
    padding: 0.5rem 0.75rem !important;
    margin: 2px 0 !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    transition: all 0.15s ease !important;
}

section[data-testid="stSidebarNav"] a:hover {
    background: var(--sb-bg-hover) !important;
    color: var(--sb-accent) !important;
}

section[data-testid="stSidebarNav"] a[aria-selected="true"] {
    background: var(--sb-bg-active) !important;
    color: var(--sb-accent) !important;
}

/* Sidebar inputs/selects */
section[data-testid="stSidebar"] .stMultiSelect > div,
section[data-testid="stSidebar"] .stSelectbox > div > div {
    background: rgba(255,255,255,0.07) !important;
    border-color: var(--sb-border) !important;
    color: var(--sb-text-strong) !important;
}

section[data-testid="stSidebar"] .stButton button {
    background: rgba(255,255,255,0.08) !important;
    border-color: var(--sb-border) !important;
    color: var(--sb-text-strong) !important;
    font-size: 0.8125rem !important;
}

section[data-testid="stSidebar"] .stButton button:hover {
    background: rgba(255,255,255,0.14) !important;
}

/* ─── Metrics ───────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: var(--c-card) !important;
    border: 1px solid var(--c-border) !important;
    border-radius: var(--r-lg) !important;
    padding: 1rem 1.25rem !important;
    box-shadow: var(--shadow-xs) !important;
}

[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-size: 1.875rem !important;
    font-weight: 700 !important;
    color: var(--c-text) !important;
    letter-spacing: -0.02em !important;
}

[data-testid="metric-container"] [data-testid="stMetricLabel"] {
    font-size: 0.8125rem !important;
    font-weight: 500 !important;
    color: var(--c-text-muted) !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}

/* ─── Chat messages ─────────────────────────────────────────────── */
[data-testid="stChatMessage"] {
    padding: 1.125rem 1.375rem !important;
    margin-bottom: 0.625rem !important;
    border-radius: var(--r-lg) !important;
    border: 1px solid var(--c-border) !important;
    background: var(--c-card) !important;
    box-shadow: var(--shadow-xs) !important;
}

[data-testid="stChatMessage"]:has([data-testid*="user"]) {
    background: var(--c-surface) !important;
}

[data-testid="stChatMessage"] p { line-height: 1.65; margin-bottom: 0.4rem; }

[data-testid="stChatMessageAvatar"] {
    width: 28px !important;
    height: 28px !important;
    border-radius: var(--r-sm) !important;
}

/* ─── Chat input ────────────────────────────────────────────────── */
[data-testid="stChatInput"] {
    border-radius: var(--r-xl) !important;
    background: var(--c-card) !important;
    border: 1.5px solid var(--c-border-strong) !important;
    box-shadow: var(--shadow-sm) !important;
}

[data-testid="stChatInput"]:focus-within {
    border-color: var(--c-accent) !important;
    box-shadow: 0 0 0 3px var(--c-accent-ring), var(--shadow-sm) !important;
}

[data-testid="stChatInput"] textarea {
    font-size: 0.9375rem !important;
    line-height: 1.5 !important;
    padding: 0.75rem 1rem !important;
}

/* ─── Buttons ───────────────────────────────────────────────────── */
.stButton button, .stDownloadButton button {
    border-radius: var(--r-md) !important;
    border: 1px solid var(--c-border-strong) !important;
    background: var(--c-card) !important;
    color: var(--c-text) !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    padding: 0.45rem 1rem !important;
    transition: all 0.15s ease !important;
    box-shadow: var(--shadow-xs) !important;
    letter-spacing: -0.005em !important;
}

.stButton button:hover, .stDownloadButton button:hover {
    background: var(--c-surface) !important;
    border-color: var(--c-text-muted) !important;
    box-shadow: var(--shadow-sm) !important;
    transform: translateY(-1px) !important;
}

.stButton button[kind="primary"] {
    background: var(--c-accent) !important;
    color: #ffffff !important;
    border-color: var(--c-accent) !important;
    box-shadow: 0 1px 3px rgba(99,102,241,0.3), var(--shadow-xs) !important;
}

.stButton button[kind="primary"]:hover {
    background: var(--c-accent-hover) !important;
    border-color: var(--c-accent-hover) !important;
    box-shadow: 0 4px 8px rgba(99,102,241,0.3) !important;
    transform: translateY(-1px) !important;
}

.stButton button[kind="secondary"] {
    border-color: var(--c-border-strong) !important;
    color: var(--c-text-muted) !important;
}

/* ─── Inputs ────────────────────────────────────────────────────── */
.stTextInput input, .stTextArea textarea {
    border-radius: var(--r-md) !important;
    border: 1.5px solid var(--c-border-strong) !important;
    background: var(--c-card) !important;
    font-size: 0.9375rem !important;
    color: var(--c-text) !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}

.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: var(--c-accent) !important;
    box-shadow: 0 0 0 3px var(--c-accent-ring) !important;
    outline: none !important;
}

.stSelectbox > div > div {
    border-radius: var(--r-md) !important;
    border: 1.5px solid var(--c-border-strong) !important;
    background: var(--c-card) !important;
}

/* ─── File uploader ─────────────────────────────────────────────── */
[data-testid="stFileUploader"] section {
    border-radius: var(--r-xl) !important;
    border: 2px dashed var(--c-border-strong) !important;
    background: var(--c-card) !important;
    padding: 3rem 2rem !important;
    text-align: center !important;
    transition: all 0.2s ease !important;
    box-shadow: var(--shadow-xs) !important;
}

[data-testid="stFileUploader"] section:hover {
    border-color: var(--c-accent) !important;
    background: var(--c-accent-light) !important;
    box-shadow: 0 0 0 3px var(--c-accent-ring) !important;
}

[data-testid="stFileUploader"] section > div > span {
    font-size: 0.9375rem !important;
    color: var(--c-text-muted) !important;
}

[data-testid="stFileUploader"] button {
    border-radius: var(--r-md) !important;
    background: var(--c-accent) !important;
    color: #fff !important;
    border-color: var(--c-accent) !important;
    font-weight: 500 !important;
}

/* ─── Expanders → Card style ────────────────────────────────────── */
[data-testid="stExpander"] {
    border: none !important;
    border-radius: var(--r-lg) !important;
    margin-bottom: 0.625rem !important;
}

[data-testid="stExpander"] details {
    border: 1.5px solid var(--c-border) !important;
    border-radius: var(--r-lg) !important;
    overflow: hidden !important;
    background: var(--c-card) !important;
    box-shadow: var(--shadow-sm) !important;
    transition: box-shadow 0.2s, border-color 0.2s !important;
}

[data-testid="stExpander"] details:hover {
    box-shadow: var(--shadow-md) !important;
    border-color: var(--c-border-strong) !important;
}

[data-testid="stExpander"] details[open] {
    box-shadow: var(--shadow-md) !important;
    border-color: var(--c-border-strong) !important;
}

[data-testid="stExpander"] summary {
    background: var(--c-card) !important;
    border: none !important;
    padding: 0.875rem 1.25rem !important;
    font-weight: 500 !important;
    font-size: 0.9375rem !important;
}

[data-testid="stExpander"] details[open] summary {
    border-bottom: 1.5px solid var(--c-border) !important;
}

[data-testid="stExpander"] details > div {
    padding: 1rem 1.25rem !important;
    background: var(--c-card) !important;
}

/* ─── Tabs ──────────────────────────────────────────────────────── */
[data-testid="stTabs"] [role="tablist"] {
    border-bottom: 1.5px solid var(--c-border) !important;
    gap: 0.25rem !important;
}

[data-testid="stTabs"] [role="tab"] {
    border-radius: var(--r-md) var(--r-md) 0 0 !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    color: var(--c-text-muted) !important;
    padding: 0.6rem 1rem !important;
    border: none !important;
}

[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: var(--c-accent) !important;
    border-bottom: 2px solid var(--c-accent) !important;
    background: transparent !important;
}

[data-testid="stTabs"] [role="tab"]:hover {
    color: var(--c-text) !important;
    background: var(--c-surface) !important;
}

/* ─── Dataframe ─────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: var(--r-md) !important;
    border: 1px solid var(--c-border) !important;
    overflow: hidden !important;
    box-shadow: var(--shadow-xs) !important;
}

/* ─── Alerts ────────────────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: var(--r-md) !important;
    border: 1px solid !important;
    font-size: 0.875rem !important;
}

.element-container [data-testid="stAlert"][data-baseweb="notification"] {
    padding: 0.875rem 1rem !important;
}

/* ─── Status widget ─────────────────────────────────────────────── */
[data-testid="stStatusWidget"] {
    border-radius: var(--r-lg) !important;
    border: 1.5px solid var(--c-border) !important;
    background: var(--c-card) !important;
    box-shadow: var(--shadow-sm) !important;
}

/* ─── Spinner ───────────────────────────────────────────────────── */
.stSpinner > div { border-top-color: var(--c-accent) !important; }

/* ─── Tags / badges ─────────────────────────────────────────────── */
.tag {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.2rem 0.6rem;
    font-size: 0.75rem;
    font-weight: 600;
    border-radius: var(--r-full);
    letter-spacing: 0.01em;
    line-height: 1.5;
    white-space: nowrap;
    background: var(--c-surface);
    color: var(--c-text-muted);
}

.tag-success { background: var(--c-success-bg); color: var(--c-success-text); }
.tag-error   { background: var(--c-error-bg);   color: var(--c-error-text);   }
.tag-info    { background: var(--c-info-bg);     color: var(--c-info-text);    }
.tag-warn    { background: var(--c-warning-bg);  color: var(--c-warning-text); }
.tag-purple  { background: var(--c-accent-light); color: var(--c-accent); }

/* Status pill with pulsing dot */
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.3rem 0.75rem;
    font-size: 0.8125rem;
    font-weight: 500;
    border-radius: var(--r-full);
    background: var(--c-surface);
    color: var(--c-text-muted);
    border: 1px solid var(--c-border);
    margin: 0.25rem 0;
}

.status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--c-text-subtle);
    flex-shrink: 0;
}

.status-dot.ok  {
    background: var(--c-success);
    box-shadow: 0 0 0 2.5px rgba(16, 185, 129, 0.2);
}
.status-dot.err {
    background: var(--c-error);
    box-shadow: 0 0 0 2.5px rgba(239, 68, 68, 0.2);
}

/* ─── Stat card (custom HTML) ───────────────────────────────────── */
.stat-card {
    background: var(--c-card);
    border: 1.5px solid var(--c-border);
    border-radius: var(--r-lg);
    padding: 1.125rem 1.25rem;
    box-shadow: var(--shadow-sm);
}

.stat-card .stat-label {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--c-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 0.375rem;
}

.stat-card .stat-value {
    font-size: 1.875rem;
    font-weight: 700;
    color: var(--c-text);
    letter-spacing: -0.03em;
    line-height: 1;
}

.stat-card .stat-sub {
    font-size: 0.8125rem;
    color: var(--c-text-subtle);
    margin-top: 0.375rem;
}

/* ─── Doc card header ───────────────────────────────────────────── */
.doc-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
}

.doc-name {
    font-size: 0.9375rem;
    font-weight: 600;
    color: var(--c-text);
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.doc-meta {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0;
    font-size: 0.8125rem;
    color: var(--c-text-subtle);
}

/* ─── Empty state ───────────────────────────────────────────────── */
.empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 4rem 2rem;
    color: var(--c-text-muted);
}

.empty-state-icon {
    width: 64px;
    height: 64px;
    border-radius: 16px;
    background: var(--c-surface);
    border: 1.5px solid var(--c-border);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.75rem;
    margin-bottom: 1.25rem;
    box-shadow: var(--shadow-sm);
}

.empty-state h2 {
    font-size: 1.125rem !important;
    font-weight: 650 !important;
    color: var(--c-text) !important;
    margin: 0 0 0.5rem !important;
}

.empty-state p {
    font-size: 0.9375rem !important;
    max-width: 34ch;
    margin: 0 !important;
}

/* ─── Page section header ───────────────────────────────────────── */
.section-header {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
    margin: 1.75rem 0 1rem;
    padding-bottom: 0.75rem;
    border-bottom: 1.5px solid var(--c-border);
}

.section-header h2 {
    margin: 0 !important;
    font-size: 1.0625rem !important;
    font-weight: 650 !important;
    color: var(--c-text) !important;
}

.section-header .section-count {
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--c-text-muted);
    background: var(--c-surface);
    border: 1px solid var(--c-border);
    border-radius: var(--r-full);
    padding: 0.15rem 0.6rem;
}

/* ─── Service status card ───────────────────────────────────────── */
.svc-card {
    background: var(--c-card);
    border: 1.5px solid var(--c-border);
    border-radius: var(--r-lg);
    padding: 1.125rem 1.25rem;
    box-shadow: var(--shadow-sm);
    margin-bottom: 0.625rem;
}

.svc-card h3 {
    font-size: 0.875rem !important;
    font-weight: 600 !important;
    color: var(--c-text) !important;
    margin: 0 0 0.25rem !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.svc-card .svc-meta {
    font-size: 0.8125rem;
    color: var(--c-text-subtle);
    margin-top: 0.5rem;
    font-family: "SF Mono", "Cascadia Code", monospace;
}

/* ─── Code & JSON ───────────────────────────────────────────────── */
.stMarkdown code {
    border-radius: var(--r-sm) !important;
    font-family: "SF Mono", "Cascadia Code", "Fira Code", monospace !important;
    font-size: 0.85em !important;
    background: var(--c-surface) !important;
    border: 1px solid var(--c-border) !important;
    padding: 0.1em 0.4em !important;
}

pre, .stCode {
    border-radius: var(--r-md) !important;
    font-family: "SF Mono", "Cascadia Code", "Fira Code", monospace !important;
    border: 1px solid var(--c-border) !important;
}

[data-testid="stJson"] {
    background: var(--c-surface) !important;
    border: 1.5px solid var(--c-border) !important;
    border-radius: var(--r-md) !important;
    padding: 1rem !important;
    font-size: 0.8125rem !important;
}

/* ─── Dividers ──────────────────────────────────────────────────── */
hr {
    border: none !important;
    height: 1.5px !important;
    background: var(--c-border) !important;
    margin: 2rem 0 !important;
}

/* ─── Scrollbar ─────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 7px; height: 7px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    background: var(--c-border-strong);
    border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover { background: var(--c-text-subtle); }

/* ─── Captions ──────────────────────────────────────────────────── */
.stApp .stCaption, [data-testid="stCaptionContainer"] {
    font-size: 0.8125rem !important;
    color: var(--c-text-muted) !important;
    line-height: 1.6 !important;
}

/* ─── Page title area ───────────────────────────────────────────── */
.page-header {
    margin-bottom: 1.75rem;
}

.page-header h1 {
    margin: 0 0 0.375rem !important;
}

.page-header p {
    font-size: 0.9375rem;
    color: var(--c-text-muted);
    margin: 0 !important;
    max-width: 62ch;
    line-height: 1.6;
}

/* ─── Source row ────────────────────────────────────────────────── */
.source-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    background: var(--c-card);
    border: 1.5px solid var(--c-border);
    border-radius: var(--r-md);
    margin-bottom: 0.5rem;
    box-shadow: var(--shadow-xs);
    transition: border-color 0.15s;
}

.source-row:hover { border-color: var(--c-border-strong); }

.source-name {
    flex: 1;
    font-size: 0.8625rem;
    font-weight: 500;
    color: var(--c-text);
    font-family: "SF Mono", "Cascadia Code", monospace;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.source-chunks {
    font-size: 0.8125rem;
    color: var(--c-text-muted);
    font-weight: 500;
    flex-shrink: 0;
}

/* ─── Config block ──────────────────────────────────────────────── */
.config-block {
    background: var(--c-surface);
    border: 1.5px solid var(--c-border);
    border-radius: var(--r-md);
    padding: 0.875rem 1rem;
    font-family: "SF Mono", "Cascadia Code", monospace;
    font-size: 0.8125rem;
    color: var(--c-text-muted);
    line-height: 1.8;
}

.config-key   { color: var(--c-text-subtle); }
.config-value { color: var(--c-text); font-weight: 500; }
</style>
"""


def inject_styles() -> None:
    """Inject the global stylesheet. Call once per page (top of script)."""
    st.markdown(_CSS, unsafe_allow_html=True)


def render_status_pill(label: str, ok: bool) -> str:
    """Return HTML for an inline status pill."""
    cls = "ok" if ok else "err"
    return (
        f'<div class="status-pill">'
        f'<span class="status-dot {cls}"></span>{label}'
        f'</div>'
    )


def render_tag(text: str, kind: str = "info") -> str:
    """Return HTML for a colored badge pill."""
    return f'<span class="tag tag-{kind}">{text}</span>'


def render_stat_card(label: str, value: str, sub: str = "") -> str:
    """Return HTML for a standalone stat card."""
    sub_html = f'<div class="stat-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="stat-card">'
        f'<div class="stat-label">{label}</div>'
        f'<div class="stat-value">{value}</div>'
        f'{sub_html}'
        f'</div>'
    )


def render_section_header(title: str, count: int | str | None = None) -> str:
    """Return HTML for a section heading with optional count badge."""
    count_html = (
        f'<span class="section-count">{count}</span>' if count is not None else ""
    )
    return (
        f'<div class="section-header">'
        f'<h2>{title}</h2>{count_html}'
        f'</div>'
    )
