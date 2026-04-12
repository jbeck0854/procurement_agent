"""
UI theme — CSS injection, logo/avatar loading, and visual helper functions.

Ported from Matthew's UI branch. All visual constants live here so
streamlit_app.py stays focused on business logic.
"""

import base64
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st

# ── Logo + avatar loading (called once at import time) ───────────────────────

_ASSETS_DIR = Path(__file__).parent.parent / "assets"

try:
    from PIL import Image as _PILImage

    LOGO_B64 = base64.b64encode((_ASSETS_DIR / "logo_python.png").read_bytes()).decode()
    FAVICON = _PILImage.open(_ASSETS_DIR / "logo_python.png")
    USER_AVATAR = _PILImage.open(_ASSETS_DIR / "user.png")
    CPU_AVATAR = _PILImage.open(_ASSETS_DIR / "cpu.png")
except (FileNotFoundError, Exception):
    LOGO_B64 = ""
    FAVICON = "⬡"
    USER_AVATAR = "user"
    CPU_AVATAR = "assistant"


# ── Glass card style (reused across streaming, plan approval, etc.) ──────────

SECTION_STYLE = (
    "background:#0A1F17;"
    "border:1px solid #333333; border-radius:2px;"
    "padding:1.25rem 1.5rem; margin-bottom:0.875rem;"
    "box-shadow:rgba(0,0,0,0.3) 0px 0px 5px;"
)


def section_header(icon: str, label: str, accent: str = "#888888") -> str:
    """Return HTML for a styled section header inside a glass card."""
    return (
        f"<div style='display:flex; align-items:center; gap:0.5rem; margin-bottom:0.875rem;'>"
        f"<span style='color:{accent}; font-size:1.0rem;'>{icon}</span>"
        f"<p style='font-family:Inter,sans-serif; font-size:0.65rem; font-weight:600; letter-spacing:0.15em;"
        f"text-transform:uppercase; color:#FFFFFF; margin:0;'>{label}</p>"
        f"</div>"
    )


def render_charts(charts: dict):
    """Render a dict of {chart_name: base64_png} in a 2-column grid."""
    items = list(charts.items())
    for i in range(0, len(items), 2):
        pair = items[i : i + 2]
        cols = st.columns(len(pair))
        for col, (chart_name, b64_img) in zip(cols, pair):
            with col:
                st.caption(chart_name.replace("_", " ").title())
                st.image(base64.b64decode(b64_img))


# ── CSS injection ────────────────────────────────────────────────────────────

def inject_css():
    """Inject the full dark-theme CSS into the Streamlit page."""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Manrope:wght@300;400;500;600;700;800&family=Inter:wght@400;500;600&display=swap');

    /* ── Base ── */
    html, body, .stApp {
        background-color: #03170F !important;
        font-family: 'Inter', sans-serif !important;
        color: #FFFFFF !important;
    }

    /* ── Hide Streamlit chrome ── */
    [data-testid="stHeader"] {
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }
    [data-testid="stDecoration"],
    [data-testid="stToolbar"],
    [data-testid="stStatusWidget"],
    footer,
    #MainMenu { display: none !important; }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background-color: #0A1F17 !important;
        border-right: 1px solid #333333 !important;
        min-width: 16rem !important;
        width: 16rem !important;
        transform: translateX(0) !important;
        transition: none !important;
    }
    section[data-testid="stSidebar"] > div:first-child {
        padding-top: 0 !important;
    }
    .stMarkdown,
    [data-testid="stMarkdownContainer"],
    [data-testid="stMarkdownContainer"] > div,
    .element-container {
        background: transparent !important;
        background-color: transparent !important;
    }
    section[data-testid="stSidebar"] .stButton > button {
        background: transparent !important;
        color: #ffffff !important;
        font-family: 'Space Grotesk', sans-serif !important;
        font-weight: 700 !important;
        font-size: 0.75rem !important;
        letter-spacing: 0.04em !important;
        text-transform: uppercase !important;
        border-radius: 2px !important;
        border: 2px solid #76b900 !important;
        width: 100% !important;
        padding: 0.6rem 1rem !important;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background: #1eaedb !important;
        border-color: #1eaedb !important;
        box-shadow: none !important;
    }

    /* ── Main content ── */
    .main .block-container {
        padding-top: 3.75rem !important;
        padding-bottom: 6rem !important;
        max-width: 1100px;
    }
    .main .block-container > div > div:first-child {
        margin-top: 0 !important;
        padding-top: 0 !important;
    }
    [data-testid="column"] > div:first-child {
        padding-top: 0 !important;
    }

    /* ── Typography ── */
    h1, h2, h3,
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
        font-family: 'Space Grotesk', sans-serif !important;
        letter-spacing: -0.02em !important;
        color: #FFFFFF !important;
    }
    p, li, .stMarkdown p {
        font-family: 'Inter', sans-serif !important;
        color: #FFFFFF !important;
        line-height: 1.65 !important;
    }

    /* ── Chat messages ── */
    @keyframes fadeInSlideUp {
        from { opacity: 0; transform: translateY(12px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .stChatMessage {
        background: #0A1F17 !important;
        border: 1px solid #333333 !important;
        border-radius: 2px !important;
        margin-bottom: 0.875rem !important;
        box-shadow: none !important;
        animation: fadeInSlideUp 0.5s cubic-bezier(0.2, 0.8, 0.2, 1) forwards !important;
    }

    .stChatMessage[data-testid="stChatMessageUser"] {
        background: #0A1F17 !important;
        border: 1px solid #333333 !important;
        border-left: 2px solid #76b900 !important;
    }

    /* ── Chat input ── */
    [data-testid="stChatInput"] {
        background: #0A1F17 !important;
        border: 1px solid #333333 !important;
        border-radius: 2px !important;
        box-shadow: none !important;
        transition: all 0.3s ease !important;
    }

    [data-testid="stChatInput"]:focus-within {
        border-color: #76b900 !important;
        box-shadow: none !important;
    }
    [data-testid="stChatInput"] textarea,
    [data-testid="stChatInputTextArea"] textarea {
        background: transparent !important;
        color: #FFFFFF !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.95rem !important;
    }
    [data-testid="stChatInput"] button[data-testid="stChatInputSubmitButton"],
    [data-testid="stChatInput"] button {
        background: transparent !important;
        color: #ffffff !important;
        border-radius: 50% !important;
        border: 2px solid #76b900 !important;
        box-shadow: none !important;
    }

    /* ── Primary buttons ── */
    .stButton > button {
        background: transparent !important;
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        border: 2px solid #76b900 !important;
        border-radius: 2px !important;
        font-family: 'Space Grotesk', sans-serif !important;
        font-weight: 700 !important;
        letter-spacing: 0.04em !important;
        text-transform: uppercase !important;
        font-size: 0.75rem !important;
        padding: 0.6rem 1.5rem !important;
        transition: background 0.2s ease, border-color 0.2s ease, transform 0.15s ease !important;
    }
    .stButton > button p,
    .stButton > button span,
    .stButton > button div {
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
    }
    .stButton > button:hover {
        background: #1eaedb !important;
        border-color: #1eaedb !important;
        box-shadow: none !important;
        transform: scale(1.02) !important;
    }
    .stButton > button:active {
        transform: scale(0.97) !important;
    }

    /* ── Text input ── */
    .stTextInput > div > div > input {
        background: transparent !important;
        border: none !important;
        border-bottom: 1px solid #888888 !important;
        border-radius: 0 !important;
        color: #FFFFFF !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.9rem !important;
        padding: 0.4rem 0 !important;
        box-shadow: none !important;
        outline: none !important;
    }
    .stTextInput > div > div > input:focus {
        border-bottom: 1px solid #76b900 !important;
        box-shadow: none !important;
    }
    .stTextInput > div > div > input::placeholder {
        color: rgba(136,136,136,0.6) !important;
    }
    .stTextInput label,
    .stTextInput > label {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.6rem !important;
        letter-spacing: 0.15em !important;
        text-transform: uppercase !important;
        color: #888888 !important;
    }

    /* ── Expander ── */
    .stExpander {
        background: #0A1F17 !important;
        border: 1px solid #333333 !important;
        border-radius: 2px !important;
        margin-top: 0.5rem !important;
    }
    .stExpander details summary {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.65rem !important;
        letter-spacing: 0.15em !important;
        text-transform: uppercase !important;
        color: #888888 !important;
    }
    .stExpander details summary:hover { color: #76b900 !important; }
    .stExpander details summary svg { color: #888888 !important; }

    /* ── Metrics ── */
    [data-testid="metric-container"] {
        background: #0A1F17 !important;
        border: 1px solid #333333 !important;
        border-radius: 2px !important;
        padding: 0.7rem 1rem !important;
    }
    [data-testid="metric-container"] label {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.55rem !important;
        letter-spacing: 0.15em !important;
        text-transform: uppercase !important;
        color: #888888 !important;
    }
    [data-testid="stMetricValue"] {
        font-family: 'Space Grotesk', sans-serif !important;
        color: #76b900 !important;
        font-size: 1.3rem !important;
        font-weight: 700 !important;
    }

    /* ── Code blocks ── */
    .stCode, .stCodeBlock, pre, code {
        background: #0A1F17 !important;
        border: 1px solid #333333 !important;
        border-radius: 2px !important;
        font-size: 0.78rem !important;
        color: #76b900 !important;
    }
    pre { padding: 0.875rem !important; }

    /* ── Divider ── */
    hr { border-color: #333333 !important; margin: 1rem 0 !important; }

    /* ── Spinner ── */
    [data-testid="stSpinner"] > div > div {
        border-top-color: #76b900 !important;
    }

    /* ── Caption ── */
    .stCaptionContainer,
    [data-testid="stCaptionContainer"],
    small, .caption {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.6rem !important;
        letter-spacing: 0.12em !important;
        text-transform: uppercase !important;
        color: #888888 !important;
    }

    /* ── Info box ── */
    [data-testid="stAlert"],
    .stInfo, .stSuccess, .stWarning {
        background: #0A1F17 !important;
        border: 1px solid #333333 !important;
        color: #ffffff !important;
        border-radius: 2px !important;
    }

    /* ── Scrollbar ── */
    ::-webkit-scrollbar { width: 4px; height: 4px; }
    ::-webkit-scrollbar-track { background: #03170F; }
    ::-webkit-scrollbar-thumb { background: #333333; border-radius: 2px; }
    ::-webkit-scrollbar-thumb:hover { background: #76b900; }

    /* ── Inline result blocks (glass cards) ── */
    .result-label {
        font-family: 'Inter', sans-serif;
        font-size: 0.6rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #888888;
        margin: 0.75rem 0 0.3rem;
    }
    .result-pre {
        background: #1a1a1a;
        border-radius: 2px;
        padding: 0.75rem 1rem;
        font-family: 'Inter', monospace;
        font-size: 0.78rem;
        color: #76b900;
        white-space: pre-wrap;
        word-break: break-word;
        overflow-x: auto;
        max-height: 220px;
        overflow-y: auto;
        margin: 0 0 0.5rem;
    }
    .summary-body p, .summary-body li {
        font-family: 'Inter', sans-serif !important;
        color: #FFFFFF !important;
        font-size: 0.9rem !important;
        line-height: 1.7 !important;
    }
    .summary-body h2, .summary-body h3 {
        font-family: 'Space Grotesk', sans-serif !important;
        color: #76b900 !important;
        margin-top: 1rem !important;
    }

    /* ── Suggestion chips ── */
    .suggestion-row .stButton > button {
        background: transparent !important;
        border: 1px solid #333333 !important;
        border-radius: 2px !important;
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.8rem !important;
        font-weight: 500 !important;
        letter-spacing: 0 !important;
        text-transform: none !important;
        padding: 0.65rem 1rem !important;
        min-height: 3rem !important;
        height: 3rem !important;
        line-height: 1.2 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        transition: border-color 0.2s, color 0.2s, box-shadow 0.2s !important;
    }
    .suggestion-row .stButton > button p,
    .suggestion-row .stButton > button span,
    .suggestion-row .stButton > button div {
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        font-size: 0.8rem !important;
        font-weight: 500 !important;
        text-transform: none !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }
    .suggestion-row .stButton > button:hover {
        border-color: #76b900 !important;
        background: transparent !important;
        box-shadow: none !important;
        transform: none !important;
    }
    .suggestion-row .stButton > button:hover p,
    .suggestion-row .stButton > button:hover span,
    .suggestion-row .stButton > button:hover div {
        color: #76b900 !important;
        -webkit-text-fill-color: #76b900 !important;
    }
    </style>
    """, unsafe_allow_html=True)


# ── Fixed top header bar ─────────────────────────────────────────────────────

def render_header():
    """Render a fixed top navigation bar with logo and brand name."""
    logo_html = (
        f"<img src='data:image/png;base64,{LOGO_B64}' "
        f"style='height:48px; width:auto; object-fit:contain; background:transparent;'/>"
        if LOGO_B64 else
        "<span style='font-size:1.4rem; color:#76b900;'>⬡</span>"
    )
    st.markdown(f"""
    <div style="position:fixed; top:0; left:0; right:0; z-index:999;
                background:#03170F;
                border-bottom:1px solid #333333;
                display:flex; align-items:center; justify-content:flex-start;
                padding:0.65rem 1.5rem; height:3.5rem;">
      <div style="display:flex; align-items:center; gap:0.75rem;">
        {logo_html}
        <span style="font-family:'Space Grotesk',sans-serif; font-size:0.9rem; font-weight:800;
                     color:#76b900; letter-spacing:0.04em; text-transform:uppercase;">
          Procurement Pilot
        </span>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Sidebar ──────────────────────────────────────────────────────────────────

def render_sidebar():
    """Render sidebar with branding, New Analysis button, and navigation."""
    logo_html = (
        f"<img src='data:image/png;base64,{LOGO_B64}' "
        f"style='width:400px; height:auto; max-width:100% !important; object-fit:contain; display:block; margin:0 auto; background:transparent;'/>"
        if LOGO_B64 else
        "<span style='font-size:1.2rem; display:block; text-align:center; color:#76b900; line-height:1;'>⬡</span>"
    )
    st.markdown(f"""
    <div style="padding:1.5rem 0.75rem 1.25rem; border-bottom:1px solid #333333; text-align:center;">
      <div style="display:flex; flex-direction:column; align-items:center; gap:0.4rem; margin-bottom:0.5rem;">
        {logo_html}
        <span style="font-family:'Inter',sans-serif; font-size:1.2rem; font-weight:700;
                     color:#76b900; letter-spacing:0.06em; text-transform:uppercase; text-align:center;">
          Procurement Pilot
        </span>
      </div>
      <p style="font-family:'Inter',sans-serif; font-size:0.7rem; letter-spacing:0.15em;
                text-transform:uppercase; color:#888888; margin:0; font-weight:400;">
        Active Sourcing Engine
      </p>
    </div>
    """, unsafe_allow_html=True)

    if st.button("＋  New Analysis", key="new_analysis"):
        if st.session_state.messages:
            first_user = next(
                (m["content"] for m in st.session_state.messages if m["role"] == "user"),
                "Untitled"
            )
            title = first_user[:55] + ("…" if len(first_user) > 55 else "")
            st.session_state.chat_history.append({
                "id": str(uuid.uuid4()),
                "title": title,
                "timestamp": datetime.now(),
                "messages": list(st.session_state.messages),
                "traces": list(st.session_state.traces),
            })
        st.session_state.messages = []
        st.session_state.traces = []
        st.session_state.thread_id = None
        st.session_state.waiting_for_approval = False
        st.session_state.pending_plan = None
        st.session_state.waiting_for_lp_approval = False
        st.session_state.pending_lp_result = None
        st.session_state.lp_partial_state = {}
        st.session_state.saved_plan = {}
        st.session_state.lp_modify_mode = False
        st.session_state.lp_modify_baseline = {}
        st.session_state.approved_lp_runs = []
        st.session_state.lp_params_history = {}
        st.session_state.last_lp_raw_full = {}
        st.session_state.show_executive_summary = False
        st.session_state.current_view = "chat"
        st.session_state.viewing_session = None
        st.rerun()

    # Nav item CSS — override global button style for sidebar nav
    st.markdown("""
    <style>
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        padding: 0.7rem 1.25rem !important;
        width: 100% !important;
        text-align: left !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.95rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.01em !important;
        text-transform: none !important;
        margin-bottom: 2px !important;
        transition: background 0.15s !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button p,
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button span,
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button div {
        color: #888888 !important;
        -webkit-text-fill-color: #888888 !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.95rem !important;
        font-weight: 500 !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover {
        background: #0A1F17 !important;
        box-shadow: none !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover p,
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover span,
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover div {
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
    }
    </style>
    """, unsafe_allow_html=True)

    view = st.session_state.current_view

    # Current Sourcing nav item
    if view == "chat":
        st.markdown("""
        <div style="display:flex; align-items:center; gap:0.7rem; padding:0.7rem 1.25rem;
                    background:#0A1F17; border-right:3px solid #76b900; margin-bottom:2px;
                    font-family:'Inter',sans-serif; font-size:0.95rem; font-weight:600;
                    color:#76b900;">
          <span>◈</span><span>Current Sourcing</span>
        </div>""", unsafe_allow_html=True)
    else:
        if st.button("◈  Current Sourcing", key="nav_chat"):
            st.session_state.current_view = "chat"
            st.session_state.viewing_session = None
            st.rerun()

    # Session History nav item
    history_count = len(st.session_state.chat_history)
    history_label = f"◷  Session History" + (f"  ({history_count})" if history_count else "")
    if view in ("history", "history_detail"):
        st.markdown("""
        <div style="display:flex; align-items:center; gap:0.7rem; padding:0.7rem 1.25rem;
                    background:#0A1F17; border-right:3px solid #76b900; margin-bottom:2px;
                    font-family:'Inter',sans-serif; font-size:0.95rem; font-weight:600;
                    color:#76b900;">
          <span>◷</span><span>Session History</span>
        </div>""", unsafe_allow_html=True)
    else:
        if st.button(history_label, key="nav_history"):
            st.session_state.current_view = "history"
            st.session_state.viewing_session = None
            st.rerun()

    # Architecture nav item
    if view == "architecture":
        st.markdown("""
        <div style="display:flex; align-items:center; gap:0.7rem; padding:0.7rem 1.25rem;
                    background:#0A1F17; border-right:3px solid #76b900; margin-bottom:2px;
                    font-family:'Inter',sans-serif; font-size:0.95rem; font-weight:600;
                    color:#76b900;">
          <span>◬</span><span>Architecture</span>
        </div>""", unsafe_allow_html=True)
    else:
        if st.button("◬  Architecture", key="nav_architecture"):
            st.session_state.current_view = "architecture"
            st.session_state.viewing_session = None
            st.rerun()

    # Status footer
    st.markdown("""
    <div style="margin-top:2rem; padding:1rem 1.25rem 0;
                border-top:1px solid #333333;">
      <p style="font-family:'Inter',sans-serif; font-size:0.72rem;
                color:#ffffff; margin:0 0 0.5rem; font-weight:500;">
        5 Agents &middot; 89 Suppliers
      </p>
      <p style="font-family:'Inter',sans-serif; font-size:0.62rem; letter-spacing:0.12em;
                text-transform:uppercase; color:#888888; margin:0;">
        v1.0.0-beta
      </p>
    </div>
    """, unsafe_allow_html=True)


# ── Architecture view ────────────────────────────────────────────────────────

def render_architecture():
    """Render interactive animated architecture flowchart — correct LangGraph topology."""
    import streamlit.components.v1 as components

    st.markdown(
        "<div style='padding:0.75rem 0 0.25rem;'>"
        "<h2 style='font-family:Inter,sans-serif; font-size:1.3rem; font-weight:700;"
        "color:#ffffff; margin:0 0 0.25rem; letter-spacing:0.02em;'>System Architecture</h2>"
        "<p style='font-family:Inter,sans-serif; font-size:0.82rem; color:#888888; margin:0;'>"
        "Hybrid orchestrator with parallel agent pipelines and intelligent routing.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    arch_html = '''<!DOCTYPE html>
<html><head><style>
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#0A1F17; overflow:hidden; font-family:Inter,system-ui,sans-serif; }
canvas { display:block; cursor:crosshair; }
#tip {
  position:absolute; display:none; pointer-events:none;
  background:rgba(10,31,23,0.95); border:1px solid #76b900; border-radius:3px;
  padding:12px 16px; font-size:12px; color:#ccc; max-width:320px;
  box-shadow:0 4px 20px rgba(0,0,0,0.5); z-index:10;
}
#tip .tl { color:#fff; font-weight:700; font-size:14px; text-transform:uppercase;
  letter-spacing:0.06em; margin-bottom:6px; }
#tip .td { color:#aaa; font-size:11.5px; margin-bottom:5px; line-height:1.55; }
#tip .tt { color:#76b900; font-size:11px; margin-top:3px; }
</style></head><body>
<canvas id="c"></canvas>
<div id="tip"></div>
<script>
var canvas = document.getElementById("c");
var ctx = canvas.getContext("2d");
var tip = document.getElementById("tip");
var DPR = window.devicePixelRatio || 1;
var TAU = Math.PI * 2;
var W, H;

function resize() {
  W = canvas.parentElement.clientWidth || 1000;
  H = 820;
  canvas.width = W * DPR;
  canvas.height = H * DPR;
  canvas.style.width = W + "px";
  canvas.style.height = H + "px";
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
}
resize();

// Agent descriptions for tooltips
var INFO = {
  orchestrator: {desc:"Hybrid LLM orchestrator. Classifies user intent via few-shot prompt, extracts parameters deterministically, generates execution plan.", tools:["LLM Intent Classification (GPT)","Few-shot Prompt (17 examples)","param_extractor.py (regex, 0ms)","interrupt() → User approves plan"]},
  pipeline_agent: {desc:"Direct-mode execution of 10 pre-built SQL query tools. No LLM in the loop — fastest path (~0.2s).", tools:["query_forecast_summary","query_component_requirements","query_aggregated_procurement_need","query_triggered_procurement_rows","+ 6 more pipeline tools"]},
  data_agent: {desc:"ReAct loop agent with free-form SQL via PostgreSQL MCP server. Autonomously decides which tables to query.", tools:["MCP PostgreSQL (SQL)","Iterative tool-calling loop","Schema-aware exploration"]},
  risk_agent: {desc:"ReAct loop agent for geopolitical risk assessment via Tavily MCP web search.", tools:["Tavily Web Search API","News analysis (30-day window)","Risk scoring: HIGH / MED / LOW"]},
  chart_agent: {desc:"Direct-mode visualization generation. 7 chart tools for supplier scoring and comparison.", tools:["plot_score_breakdown","plot_supplier_comparison","plot_country_comparison","plot_price_trend","+ 3 more chart tools"]},
  lp_agent: {desc:"Linear programming optimizer using PuLP/CBC solver. Balances cost vs supply risk under constraints.", tools:["run_optimization(product, lambda_risk, ...)","PuLP/CBC Solver","interrupt() → LP approval / modify / discard"]},
  synthesizer: {desc:"LLM-powered final response. Only runs for Data/Risk agent flows (free-form text). Pipeline/Chart/LP skip this node.", tools:["GPT summary generation","Cross-cutting insights","2-3 sentence executive summary"]},
  router: {desc:"Routing node. Fans results from Phase 1 into Phase 2 agents. Decides if Synthesizer is needed based on which agents participated.", tools:["Conditional routing logic","Data/Risk → needs Synthesizer","Pipeline/Chart/LP → skip to END"]},
};

// ── Node layout (vertical, LARGER) ──
var NW = 140, NH = 44, OW = 115, OH = 36;
var RG = 90, CG = 30;
var cx = W / 2;

// Row Y positions (more spacing)
var RY = {
  user: 40,
  orch: 40 + RG,
  phase1: 40 + RG * 2,
  router: 40 + RG * 3,
  phase2: 40 + RG * 4,
  synth: 40 + RG * 5.5,
  end: 40 + RG * 6.5,
  resp: 40 + RG * 7.5,
};

var nodes = [
  // Row 0: User
  {id:"user", label:"User Input", cx:cx, cy:RY.user, w:NW, h:NH, key:null},
  // Row 1: Orchestrator (sequential internal flow)
  {id:"orch_classify", label:"LLM Classify", cx:cx-OW-CG, cy:RY.orch, w:OW, h:OH, key:"orchestrator"},
  {id:"orch_fewshot", label:"Few-Shot", cx:cx, cy:RY.orch, w:OW, h:OH, key:"orchestrator"},
  {id:"orch_extract", label:"Param Extract", cx:cx+OW+CG, cy:RY.orch, w:OW, h:OH, key:"orchestrator"},
  // Row 2: Phase 1 (parallel fan-out)
  {id:"pipeline_agent", label:"Pipeline Agent", cx:cx-(NW+CG), cy:RY.phase1, w:NW, h:NH, key:"pipeline_agent"},
  {id:"data_agent", label:"Data Agent", cx:cx, cy:RY.phase1, w:NW, h:NH, key:"data_agent"},
  {id:"risk_agent", label:"Risk Agent", cx:cx+(NW+CG), cy:RY.phase1, w:NW, h:NH, key:"risk_agent"},
  // Row 3: Router (fan-in)
  {id:"router", label:"Phase Router", cx:cx, cy:RY.router, w:NW, h:36, key:"router"},
  // Row 4: Phase 2 (parallel fan-out)
  {id:"chart_agent", label:"Chart Agent", cx:cx-(NW/2+CG/2), cy:RY.phase2, w:NW, h:NH, key:"chart_agent"},
  {id:"lp_agent", label:"LP Optimizer", cx:cx+(NW/2+CG/2), cy:RY.phase2, w:NW, h:NH, key:"lp_agent"},
  // Row 5: Synthesizer (conditional)
  {id:"synthesizer", label:"Synthesizer", cx:cx, cy:RY.synth, w:NW, h:NH, key:"synthesizer"},
  // Row 6: END
  {id:"end_node", label:"END", cx:cx+(NW+CG), cy:RY.end, w:80, h:34, key:null},
  // Row 7: Response
  {id:"response", label:"Response", cx:cx, cy:RY.resp, w:NW, h:NH, key:null},
];
nodes.forEach(function(n) { n.x = n.cx - n.w/2; n.y = n.cy - n.h/2; });

var nodeMap = {};
nodes.forEach(function(n) { nodeMap[n.id] = n; });

var rowOf = {user:0, orch_classify:1, orch_fewshot:1, orch_extract:1,
  pipeline_agent:2, data_agent:2, risk_agent:2, router:3,
  chart_agent:4, lp_agent:4, synthesizer:5.5, end_node:6.5, response:7.5};

// ── Correct LangGraph edges ──
// User → Orchestrator (single entry, internal sequential)
// Orchestrator → Phase 1 (conditional fan-out)
// Phase 1 → Router (all converge)
// Router → Phase 2 (conditional fan-out) OR Synthesizer OR END
// Phase 2 → Synthesizer (if data/risk participated) OR END
// Synthesizer → END → Response
var EDGES = [
  // User → Orchestrator (enters at first sub-node)
  ["user","orch_classify"],
  // Orchestrator internal: sequential
  ["orch_classify","orch_fewshot"],
  ["orch_fewshot","orch_extract"],
  // Orchestrator → Phase 1 (fan-out from last sub-node)
  ["orch_extract","pipeline_agent"],
  ["orch_extract","data_agent"],
  ["orch_extract","risk_agent"],
  // Phase 1 → Router (fan-in)
  ["pipeline_agent","router"],
  ["data_agent","router"],
  ["risk_agent","router"],
  // Router → Phase 2 (fan-out)
  ["router","chart_agent"],
  ["router","lp_agent"],
  // Phase 2 → Synthesizer (if data/risk participated)
  ["chart_agent","synthesizer"],
  ["lp_agent","synthesizer"],
  // Direct to END (Pipeline/Chart/LP skip synthesizer)
  ["chart_agent","end_node"],
  ["lp_agent","end_node"],
  ["router","end_node"],
  // Synthesizer → Response
  ["synthesizer","response"],
  // END → Response
  ["end_node","response"],
];

// For orchestrator internal edges, connect right side → left side (horizontal)
var edges = EDGES.map(function(e) {
  var a = nodeMap[e[0]], b = nodeMap[e[1]];
  if (!a || !b) return null;
  var isHoriz = (a.cy === b.cy); // same row = horizontal
  if (isHoriz) {
    return {x1:a.cx+a.w/2, y1:a.cy, x2:b.cx-b.w/2, y2:b.cy, fromRow:rowOf[e[0]]||0, horiz:true};
  }
  return {x1:a.cx, y1:a.cy+a.h/2, x2:b.cx, y2:b.cy-b.h/2, fromRow:rowOf[e[0]]||0, horiz:false};
}).filter(Boolean);

// Particles (2 per edge)
var particles = [];
edges.forEach(function(e) {
  for (var i = 0; i < 2; i++) {
    particles.push({edge:e, offset:i/2, speed:0.3+Math.random()*0.25});
  }
});

// Drawing helpers
function drawRR(x,y,w,h,r) {
  ctx.beginPath();
  ctx.moveTo(x+r,y); ctx.lineTo(x+w-r,y); ctx.arcTo(x+w,y,x+w,y+r,r);
  ctx.lineTo(x+w,y+h-r); ctx.arcTo(x+w,y+h,x+w-r,y+h,r);
  ctx.lineTo(x+r,y+h); ctx.arcTo(x,y+h,x,y+h-r,r);
  ctx.lineTo(x,y+r); ctx.arcTo(x,y,x+r,y,r); ctx.closePath();
}
function clamp(v,a,b) { return Math.max(a,Math.min(b,v)); }
function easeOut(t) { return 1-Math.pow(1-t,3); }

// Hover
var hoverNode = null;
canvas.addEventListener("mousemove", function(evt) {
  var rect = canvas.getBoundingClientRect();
  var mx = evt.clientX - rect.left, my = evt.clientY - rect.top;
  hoverNode = null;
  for (var i = 0; i < nodes.length; i++) {
    var n = nodes[i];
    if (mx >= n.x && mx <= n.x+n.w && my >= n.y && my <= n.y+n.h) { hoverNode = n; break; }
  }
  if (hoverNode) {
    var key = hoverNode.key;
    var html = '<div class="tl">' + hoverNode.label + '</div>';
    if (key && INFO[key]) {
      html += '<div class="td">' + INFO[key].desc + '</div>';
      INFO[key].tools.forEach(function(t) { html += '<div class="tt">' + t + '</div>'; });
    }
    if (hoverNode.id === "user") html += '<div class="td">Natural language query input via Streamlit chat interface.</div>';
    if (hoverNode.id === "response") html += '<div class="td">Text + Charts + Structured Data returned to user.</div>';
    if (hoverNode.id === "end_node") html += '<div class="td">Direct output path. Pipeline/Chart/LP results skip Synthesizer for speed (~4s vs ~12s).</div>';
    tip.innerHTML = html;
    tip.style.display = "block";
    var tx = mx + 14, ty = my - 10;
    if (tx + 320 > W) tx = mx - 330;
    if (ty + 180 > H) ty = my - 180;
    tip.style.left = tx + "px";
    tip.style.top = ty + "px";
  } else { tip.style.display = "none"; }
});
canvas.addEventListener("mouseleave", function() { tip.style.display = "none"; });

// Animation
var ANIM_DUR = 3000;
var startTime = null;

function draw(ts) {
  if (!startTime) startTime = ts;
  var elapsed = ts - startTime;
  var progress = clamp(elapsed / ANIM_DUR, 0, 1);

  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = "#0A1F17";
  ctx.fillRect(0, 0, W, H);

  // Orchestrator group box
  var orchNs = nodes.filter(function(n) { return n.key === "orchestrator"; });
  if (orchNs.length) {
    var pad = 14;
    var gx = Math.min.apply(null, orchNs.map(function(n){return n.x})) - pad;
    var gy = Math.min.apply(null, orchNs.map(function(n){return n.y})) - 24;
    var gw = Math.max.apply(null, orchNs.map(function(n){return n.x+n.w})) - gx + pad;
    var gh = Math.max.apply(null, orchNs.map(function(n){return n.y+n.h})) - gy + pad;
    var gA = easeOut(clamp(progress*3,0,1));
    ctx.save();
    ctx.globalAlpha = gA * 0.12;
    drawRR(gx, gy, gw, gh, 4);
    ctx.fillStyle = "#76b900";
    ctx.fill();
    ctx.globalAlpha = gA * 0.45;
    ctx.setLineDash([5,3]); ctx.strokeStyle = "#76b900"; ctx.lineWidth = 1;
    ctx.stroke(); ctx.setLineDash([]);
    ctx.globalAlpha = gA * 0.65;
    ctx.font = "700 10px Inter,sans-serif"; ctx.fillStyle = "#76b900";
    ctx.textAlign = "left";
    ctx.fillText("ORCHESTRATOR", gx+8, gy+14);
    ctx.restore();
  }

  // Phase labels
  var phases = [{y:RY.phase1, label:"PHASE 1 — PARALLEL DATA RETRIEVAL"}, {y:RY.phase2, label:"PHASE 2 — ANALYSIS & OPTIMIZATION"}];
  phases.forEach(function(pl) {
    var a = easeOut(clamp((progress-0.15)*3,0,1));
    ctx.save(); ctx.globalAlpha = a*0.4;
    ctx.font = "700 9px Inter,sans-serif"; ctx.fillStyle = "#76b900";
    ctx.textAlign = "center";
    ctx.fillText(pl.label, cx, pl.y - NH/2 - 12);
    ctx.restore();
  });

  // Edges
  edges.forEach(function(e) {
    var delay = e.fromRow * 0.08;
    var ep = easeOut(clamp((progress - delay) / 0.25, 0, 1));
    if (ep <= 0) return;
    ctx.beginPath();
    if (e.horiz) {
      // Horizontal edge (orchestrator internal): straight line
      var ex = e.x1 + (e.x2 - e.x1) * ep;
      ctx.moveTo(e.x1, e.y1);
      ctx.lineTo(ex, e.y2);
    } else {
      // Vertical edge: bezier curve
      var my = (e.y1 + e.y2) / 2;
      ctx.moveTo(e.x1, e.y1);
      if (ep < 1) {
        var steps = 20;
        for (var i = 1; i <= Math.floor(steps*ep); i++) {
          var t = i/steps, u = 1-t;
          var px = u*u*u*e.x1 + 3*u*u*t*e.x1 + 3*u*t*t*e.x2 + t*t*t*e.x2;
          var py = u*u*u*e.y1 + 3*u*u*t*my + 3*u*t*t*my + t*t*t*e.y2;
          ctx.lineTo(px, py);
        }
      } else {
        ctx.bezierCurveTo(e.x1, my, e.x2, my, e.x2, e.y2);
      }
    }
    ctx.strokeStyle = "rgba(118,185,0,0.3)";
    ctx.lineWidth = 1.5;
    ctx.stroke();
  });

  // Flowing particles (continuous)
  if (progress > 0.25) {
    var pA = clamp((progress-0.25)/0.15, 0, 1);
    particles.forEach(function(p) {
      var e = p.edge;
      var cycle = 2200 / p.speed;
      var t = ((elapsed + p.offset*cycle) % cycle) / cycle;
      var px, py;
      if (e.horiz) {
        px = e.x1 + (e.x2 - e.x1) * t;
        py = e.y1;
      } else {
        var my = (e.y1+e.y2)/2;
        var u = 1-t;
        px = u*u*u*e.x1 + 3*u*u*t*e.x1 + 3*u*t*t*e.x2 + t*t*t*e.x2;
        py = u*u*u*e.y1 + 3*u*u*t*my + 3*u*t*t*my + t*t*t*e.y2;
      }
      var grad = ctx.createRadialGradient(px,py,0, px,py,8);
      grad.addColorStop(0, "rgba(118,185,0,"+(0.5*pA)+")");
      grad.addColorStop(1, "rgba(118,185,0,0)");
      ctx.fillStyle = grad;
      ctx.fillRect(px-8, py-8, 16, 16);
      ctx.beginPath();
      ctx.arc(px, py, 2.5, 0, TAU);
      ctx.fillStyle = "rgba(118,185,0,"+(0.85*pA)+")";
      ctx.fill();
    });
  }

  // Nodes
  nodes.forEach(function(n) {
    var row = rowOf[n.id] || 0;
    var delay = row * 0.1;
    var np = easeOut(clamp((progress - delay) / 0.2, 0, 1));
    if (np <= 0) return;
    var scale = 0.75 + 0.25 * np;
    ctx.save();
    ctx.globalAlpha = np;
    ctx.translate(n.cx, n.cy);
    ctx.scale(scale, scale);
    ctx.translate(-n.cx, -n.cy);
    var isTerminal = !n.key;

    // Glow
    if (!isTerminal && progress > 0.5) {
      var pulse = 0.5 + 0.5 * Math.sin(elapsed/500);
      var gs = 10 + pulse*5;
      var grad = ctx.createRadialGradient(n.cx,n.cy,0, n.cx,n.cy,n.w/2+gs);
      grad.addColorStop(0, "rgba(118,185,0,"+(0.06+pulse*0.03)+")");
      grad.addColorStop(1, "rgba(118,185,0,0)");
      ctx.fillStyle = grad;
      ctx.fillRect(n.x-gs, n.y-gs, n.w+gs*2, n.h+gs*2);
    }

    drawRR(n.x, n.y, n.w, n.h, 3);
    ctx.fillStyle = "rgba(10,31,23,0.9)";
    ctx.fill();
    ctx.strokeStyle = isTerminal ? "#555" : "#76b900";
    ctx.lineWidth = isTerminal ? 1 : 2;
    ctx.stroke();

    ctx.font = "700 " + (n.h < 38 ? "10" : "12") + "px Inter,sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillStyle = isTerminal ? "#999" : "#fff";
    ctx.fillText(n.label.toUpperCase(), n.cx, n.cy);

    ctx.restore();
  });

  // Footer labels
  if (progress > 0.8) {
    var ba = clamp((progress-0.8)/0.2, 0, 1);
    ctx.save(); ctx.globalAlpha = ba;
    ctx.font = "600 9px Inter,sans-serif";
    ctx.textAlign = "center"; ctx.fillStyle = "#555";
    ctx.fillText("HOVER NODES FOR DETAILS", cx, H - 10);
    ctx.restore();
  }

  requestAnimationFrame(draw);
}
requestAnimationFrame(draw);
</script></body></html>'''

    components.html(arch_html, height=830)


# ── Landing page ─────────────────────────────────────────────────────────────

def render_landing():
    """Render the landing page with metrics panel and suggestion chips."""
    _, center, _ = st.columns([1, 3, 1])
    with center:
        logo_img_html = (
            f"<img src='data:image/png;base64,{LOGO_B64}' "
            f"style='height:auto; width:420px; max-width:none !important; object-fit:contain; display:block; margin-left:auto; margin-right:auto; margin-bottom:1.5rem; transform: scale(1.15); transform-origin: center; "
            f"background:transparent;'/>"
            if LOGO_B64 else ""
        )
        st.markdown(f"""
        <div style="text-align:center; padding:0 1rem 0.75rem;">
          <div style="margin-bottom:0;">
            {logo_img_html}
          </div>
          <p style="font-family:'Manrope',sans-serif; font-size:0.95rem; color:#ffffff;
                    max-width:460px; margin:0 auto 2rem; line-height:1.65;">
            Analyzing suppliers, pricing signals, and logistics across 40+ markets
            with real-time risk assessment.
          </p>
        </div>
        """, unsafe_allow_html=True)

        # Intelligence panel
        st.markdown("""
        <div style="background:#0A1F17;
                    border:1px solid #333333; border-radius:2px;
                    padding:1.75rem 2rem; margin-bottom:1.5rem;">
          <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:1.5rem; margin-bottom:1.5rem;">
            <div>
              <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.15em;
                        text-transform:uppercase; color:#888888; margin-bottom:0.2rem;">Suppliers Indexed</p>
              <p style="font-family:'Space Grotesk',sans-serif; font-size:1.7rem; font-weight:700;
                        color:#76b900; margin:0; line-height:1.1;">89</p>
            </div>
            <div>
              <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.15em;
                        text-transform:uppercase; color:#888888; margin-bottom:0.2rem;">Countries Scanned</p>
              <p style="font-family:'Space Grotesk',sans-serif; font-size:1.7rem; font-weight:700;
                        color:#FFFFFF; margin:0; line-height:1.1;">21</p>
            </div>
            <div>
              <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.15em;
                        text-transform:uppercase; color:#888888; margin-bottom:0.2rem;">Forecast Horizon</p>
              <p style="font-family:'Space Grotesk',sans-serif; font-size:1.7rem; font-weight:700;
                        color:#ffffff; margin:0; line-height:1.1;">20<span style="font-size:0.9rem; font-weight:500;"> wks</span></p>
            </div>
            <div>
              <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.15em;
                        text-transform:uppercase; color:#888888; margin-bottom:0.2rem;">Service Level</p>
              <p style="font-family:'Space Grotesk',sans-serif; font-size:1.7rem; font-weight:700;
                        color:#76b900; margin:0; line-height:1.1;">
                90<span style="font-size:0.9rem; font-weight:500;">%</span>
              </p>
            </div>
          </div>
          <div style="display:flex; align-items:center; justify-content:center; gap:0.5rem;">
            <span style="width:6px; height:6px; border-radius:50%; background:#76b900;
                         animation:pulse 2s ease-in-out infinite;"></span>
            <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.28em;
                      text-transform:uppercase; color:rgba(118,185,0,0.55); margin:0;">
              System Ready for Query
            </p>
          </div>
        </div>
        <style>
          @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
          }
        </style>
        """, unsafe_allow_html=True)

        # Suggestion chips
        st.markdown("""
        <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.18em;
                  text-transform:uppercase; color:#888888; margin:0.25rem 0 0.75rem; text-align:center;">
          Try asking
        </p>
        """, unsafe_allow_html=True)

        _SUGGESTIONS = [
            ("Data Agent — Supplier Risk",   "Which suppliers have the highest disruption risk scores and what countries are they in?"),
            ("Risk Agent — Geopolitical",    "Are there any recent geopolitical risks affecting semiconductor supply chains in East Asia?"),
        ]
        st.markdown("<div class='suggestion-row'>", unsafe_allow_html=True)
        cols = st.columns(2)
        for col, (label, query) in zip(cols, _SUGGESTIONS):
            with col:
                if st.button(label, key=f"sug_{label[:18]}", use_container_width=True):
                    st.session_state.suggested_query = query
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


# ── Session history views ────────────────────────────────────────────────────

def render_history_list():
    """Render a list of previously saved analysis sessions."""
    st.markdown("""
    <div style="padding:1.5rem 0 1rem;">
      <h2 style="font-family:'Space Grotesk',sans-serif; font-size:1.4rem; font-weight:700;
                 color:#FFFFFF; margin-bottom:0.25rem;">Session History</h2>
      <p style="font-family:'Manrope',sans-serif; font-size:0.85rem; color:#888888; margin:0;">
        Previously saved analyses — click any to review.
      </p>
    </div>
    """, unsafe_allow_html=True)

    history = st.session_state.chat_history
    if not history:
        st.markdown("""
        <div style="background:#0A1F17; border:1px solid #333333;
                    border-radius:2px; padding:2rem; text-align:center; color:#888888;
                    font-family:'Manrope',sans-serif; font-size:0.9rem;">
          No saved sessions yet. Start a new analysis and click <strong>＋ New Analysis</strong>
          to archive it here.
        </div>
        """, unsafe_allow_html=True)
        return

    for i, session in enumerate(reversed(history)):
        idx = len(history) - 1 - i
        ts = session["timestamp"].strftime("%b %d, %Y  %H:%M")
        msg_count = sum(1 for m in session["messages"] if m["role"] == "user")
        col_text, col_btn = st.columns([5, 1])
        with col_text:
            st.markdown(f"""
            <div style="background:#0A1F17; border:1px solid #333333;
                        border-radius:2px; padding:0.85rem 1.1rem; margin-bottom:0.5rem;">
              <p style="font-family:'Space Grotesk',sans-serif; font-size:0.9rem; font-weight:600;
                        color:#FFFFFF; margin:0 0 0.2rem;">{session['title']}</p>
              <p style="font-family:'Inter',sans-serif; font-size:0.7rem; color:#888888;
                        letter-spacing:0.06em; margin:0;">
                {ts} &nbsp;·&nbsp; {msg_count} quer{"y" if msg_count == 1 else "ies"}
              </p>
            </div>""", unsafe_allow_html=True)
        with col_btn:
            st.markdown("<div style='padding-top:0.4rem;'></div>", unsafe_allow_html=True)
            if st.button("Open", key=f"open_session_{idx}"):
                st.session_state.viewing_session = idx
                st.session_state.current_view = "history_detail"
                st.rerun()


def render_history_detail(show_trace_fn):
    """Render a read-only replay of a saved session.

    Parameters
    ----------
    show_trace_fn : callable
        The show_trace function from streamlit_app.py (to avoid circular import).
    """
    idx = st.session_state.viewing_session
    session = st.session_state.chat_history[idx]
    ts = session["timestamp"].strftime("%b %d, %Y  %H:%M")

    col_back, col_title = st.columns([1, 6])
    with col_back:
        if st.button("← Back", key="history_back"):
            st.session_state.current_view = "history"
            st.session_state.viewing_session = None
            st.rerun()
    with col_title:
        st.markdown(f"""
        <div style="padding-top:0.25rem;">
          <p style="font-family:'Space Grotesk',sans-serif; font-size:1rem; font-weight:700;
                    color:#FFFFFF; margin:0;">{session['title']}</p>
          <p style="font-family:'Inter',sans-serif; font-size:0.68rem; color:#888888;
                    letter-spacing:0.06em; margin:0;">{ts} — read-only</p>
        </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:0.75rem;'></div>", unsafe_allow_html=True)

    traces = session.get("traces", [])
    assistant_index = 0
    for msg in session["messages"]:
        _avatar = USER_AVATAR if msg["role"] == "user" else CPU_AVATAR
        with st.chat_message(msg["role"], avatar=_avatar):
            if msg.get("content"):
                st.markdown(msg["content"])
            if msg.get("has_trace") and assistant_index < len(traces):
                chart_results = traces[assistant_index].get("chart_results") or {}
                if chart_results:
                    st.markdown(
                        "<div style='margin:0.75rem 0 0.35rem;'>"
                        + section_header("◎", "Visualizations", "#76b900")
                        + "</div>",
                        unsafe_allow_html=True,
                    )
                    render_charts(chart_results)
                if msg.get("summary"):
                    st.markdown(msg["summary"])
        if msg.get("has_trace") and assistant_index < len(traces):
            show_trace_fn(traces[assistant_index])
            assistant_index += 1
