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
    "padding:1.5rem 1.75rem; margin-bottom:0.875rem;"
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
        # Reset demo stepper to Initialization
        st.session_state.demo_completed_stages = set()
        st.session_state.demo_prompt = 0
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

    # Data Pipeline nav item
    if view == "data_pipeline":
        st.markdown("""
        <div style="display:flex; align-items:center; gap:0.7rem; padding:0.7rem 1.25rem;
                    background:#0A1F17; border-right:3px solid #76b900; margin-bottom:2px;
                    font-family:'Inter',sans-serif; font-size:0.95rem; font-weight:600;
                    color:#76b900;">
          <span>◊</span><span>Data Pipeline</span>
        </div>""", unsafe_allow_html=True)
    else:
        if st.button("◊  Data Pipeline", key="nav_data_pipeline"):
            st.session_state.current_view = "data_pipeline"
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
canvas { display:block; cursor:default; }
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
#panel, #panel-orch, #panel-data, #panel-risk, #panel-lp, #panel-chart {
  position:absolute; display:none; top:4%; left:5%; width:90%; height:92%;
  background:rgba(10,31,23,0.97); border:1.5px solid #76b900; border-radius:6px;
  padding:28px 32px 24px; box-shadow:0 12px 48px rgba(0,0,0,0.7); z-index:20;
  overflow-y:auto;
}
#panel .pclose, #panel-orch .pclose, #panel-data .pclose, #panel-risk .pclose, #panel-lp .pclose, #panel-chart .pclose {
  position:absolute; top:14px; right:18px; font-size:22px; color:#76b900;
  cursor:pointer; font-weight:400; line-height:1; padding:4px 10px;
  border:1px solid transparent; border-radius:3px; transition:border-color 0.15s;
}
#panel .pclose:hover, #panel-orch .pclose:hover, #panel-data .pclose:hover, #panel-risk .pclose:hover, #panel-lp .pclose:hover, #panel-chart .pclose:hover { border-color:#76b900; }
#panel .ph, #panel-orch .ph, #panel-data .ph, #panel-risk .ph, #panel-lp .ph, #panel-chart .ph { color:#fff; font-size:22px; font-weight:700; letter-spacing:0.06em;
  text-transform:uppercase; margin-bottom:6px; }
#panel .psub, #panel-orch .psub, #panel-data .psub, #panel-risk .psub, #panel-lp .psub, #panel-chart .psub { color:#888; font-size:14px; margin-bottom:26px; }
#panel .pla-flow { display:flex; flex-direction:column; gap:8px; margin-top:14px; }
#panel .pla-col { display:flex; flex-direction:column;
  background:rgba(118,185,0,0.04); border:1px solid rgba(118,185,0,0.35);
  border-radius:5px; padding:20px 26px; }
#panel .pla-h { color:#fff; font-size:17px; font-weight:700;
  letter-spacing:0.12em; text-transform:uppercase; margin-bottom:14px;
  display:flex; align-items:center; gap:16px; }
#panel .pla-n { color:#76b900; font-size:14px; font-weight:700;
  background:rgba(118,185,0,0.15); border:1.5px solid #76b900;
  padding:3px 13px; border-radius:12px; letter-spacing:normal; }
#panel .pla-inner { display:grid; grid-template-columns:1fr 360px;
  gap:28px; align-items:start; }
#panel .pla-list { list-style:none; padding:0; margin:0;
  display:flex; flex-direction:column; gap:4px; }
#panel .pla-list li { display:flex; align-items:center; gap:14px;
  padding:10px 14px; border-radius:3px; cursor:help;
  transition:background 0.15s; }
#panel .pla-list li:hover { background:rgba(118,185,0,0.12); }
#panel .pla-num { color:#76b900; font-size:13px; font-weight:700;
  font-family:'SF Mono',Menlo,Consolas,monospace; opacity:0.75;
  min-width:22px; }
#panel .pla-name { color:#fff; font-size:17px; font-weight:500;
  font-family:'SF Mono',Menlo,Consolas,monospace; }
#panel .pla-sql-side { border-left:1px dashed rgba(118,185,0,0.28);
  padding-left:22px; align-self:stretch; }
#panel .pla-vlabel { color:#888; font-size:12px; font-weight:700;
  letter-spacing:0.14em; text-transform:uppercase; margin-bottom:10px; }
#panel .pla-views { display:flex; flex-direction:column; gap:6px; }
#panel .pla-view { color:#76b900; font-size:14px;
  font-family:'SF Mono',Menlo,Consolas,monospace;
  background:rgba(118,185,0,0.08); padding:8px 12px; border-radius:2px;
  border-left:3px solid rgba(118,185,0,0.6); opacity:0.92; }
#panel .pla-arr { text-align:center; color:#76b900;
  font-size:32px; font-weight:700; line-height:1; margin:2px 0; }
#panel-orch .gsec, #panel-data .gsec, #panel-risk .gsec, #panel .gsec, #panel-lp .gsec, #panel-chart .gsec { margin-bottom:32px; }
#panel-orch .gsec-n, #panel-data .gsec-n, #panel-risk .gsec-n, #panel .gsec-n, #panel-lp .gsec-n, #panel-chart .gsec-n { color:#76b900; font-size:11px; font-weight:700; letter-spacing:0.14em;
  text-transform:uppercase; margin-bottom:4px; }
#panel-orch .gsec-t, #panel-data .gsec-t, #panel-risk .gsec-t, #panel .gsec-t, #panel-lp .gsec-t, #panel-chart .gsec-t { color:#fff; font-size:18px; font-weight:700; margin-bottom:16px;
  letter-spacing:0.02em; }
#panel-orch .fan-svg, #panel-data .fan-svg, #panel-risk .fan-svg, #panel .fan-svg, #panel-lp .fan-svg, #panel-chart .fan-svg { width:100%; height:auto; display:block; }
#panel-orch .ex-flow { display:grid; grid-template-columns:1fr 40px auto;
  gap:16px; align-items:center; padding:10px 0;
  border-top:1px dashed rgba(118,185,0,0.15); }
#panel-orch .ex-flow:first-of-type { border-top:none; padding-top:4px; }
#panel-orch .ex-q { color:#ddd; font-size:14px; font-style:italic;
  background:rgba(255,255,255,0.04); border-left:3px solid #555; padding:10px 14px;
  border-radius:0 3px 3px 0; }
#panel-orch .ex-arr { color:#76b900; font-size:20px; font-weight:700; text-align:center; }
#panel-orch .ex-chip { display:inline-block; padding:7px 14px;
  background:rgba(118,185,0,0.12); border:1.5px solid #76b900;
  border-radius:3px; color:#76b900; font-size:13px; font-weight:600;
  font-family:'SF Mono',Menlo,Consolas,monospace; white-space:nowrap; }
#panel-orch .pm-row { display:grid; grid-template-columns:180px 1fr 30px auto;
  gap:16px; align-items:center; padding:12px 0;
  border-top:1px dashed rgba(118,185,0,0.15); }
#panel-orch .pm-row:first-of-type { border-top:none; padding-top:4px; }
#panel-orch .pm-field { color:#76b900; font-size:13.5px; font-weight:600;
  font-family:'SF Mono',Menlo,Consolas,monospace; }
#panel-orch .pm-in { color:#999; font-size:14px; font-style:italic; }
#panel-orch .pm-in mark { background:rgba(118,185,0,0.22); color:#76b900;
  padding:2px 6px; border-radius:2px; font-weight:700; font-style:normal;
  font-family:'SF Mono',Menlo,Consolas,monospace; font-size:13px; }
#panel-orch .pm-arr { color:#76b900; font-size:18px; font-weight:700; text-align:center; }
#panel-orch .pm-out { color:#fff; font-size:13px; font-weight:600;
  font-family:'SF Mono',Menlo,Consolas,monospace;
  background:rgba(118,185,0,0.18); border:1px solid #76b900;
  padding:7px 14px; border-radius:3px; text-align:center;
  white-space:nowrap; }
#panel-orch .tl { display:flex; align-items:center; gap:10px; flex-wrap:wrap;
  padding:14px 0 10px; }
#panel-orch .tl-step { padding:10px 16px; border:1.5px solid #76b900;
  border-radius:3px; color:#fff; font-size:13px; font-weight:600;
  background:rgba(118,185,0,0.06); font-family:'SF Mono',Menlo,Consolas,monospace; }
#panel-orch .tl-pause { padding:10px 16px; border:1.5px solid #e0a020;
  border-radius:3px; color:#e0a020; font-size:13px; font-weight:600;
  background:rgba(224,160,32,0.06); }
#panel-orch .tl-ok { padding:10px 16px; border:1.5px solid #76b900;
  border-radius:3px; color:#76b900; font-size:13px; font-weight:600;
  background:rgba(118,185,0,0.12); }
#panel-orch .tl-reject { padding:10px 16px; border:1.5px solid #c04040;
  border-radius:3px; color:#c04040; font-size:13px; font-weight:600;
  background:rgba(192,64,64,0.08); }
#panel-orch .tl-arr { color:#76b900; font-size:18px; font-weight:700; }
#panel-orch .tl-caption { color:#888; font-size:12.5px; margin-top:8px;
  font-style:italic; }
#panel-data .tl-caption { color:#888; font-size:12.5px; margin-top:12px;
  font-style:italic; text-align:center; }
#panel-data .da-two { display:grid; grid-template-columns:1fr 1.4fr; gap:28px;
  align-items:start; }
#panel-data .da-h-small { color:#76b900; font-size:12px; font-weight:700;
  letter-spacing:0.14em; text-transform:uppercase; margin-bottom:12px; }
#panel-data .da-tool { background:rgba(118,185,0,0.04);
  border:1px solid rgba(118,185,0,0.35); border-radius:4px;
  padding:14px 16px; margin-bottom:12px; }
#panel-data .da-tool-name { color:#76b900; font-size:15px; font-weight:600;
  font-family:'SF Mono',Menlo,Consolas,monospace; margin-bottom:6px; }
#panel-data .da-tool-desc { color:#bbb; font-size:12.5px; line-height:1.55; }
#panel-data .da-schema-group { margin-bottom:14px; }
#panel-data .da-gk { color:#fff; font-size:12.5px; font-weight:700;
  text-transform:uppercase; letter-spacing:0.1em; margin-bottom:6px; }
#panel-data .da-gv { display:flex; flex-wrap:wrap; gap:6px; }
#panel-data .da-chip { display:inline-block; padding:5px 11px;
  background:rgba(118,185,0,0.08); border:1px solid rgba(118,185,0,0.45);
  border-radius:3px; color:#76b900; font-size:12px;
  font-family:'SF Mono',Menlo,Consolas,monospace; }
#panel-data .da-trace { display:flex; flex-direction:column; gap:10px;
  background:rgba(0,0,0,0.2); border:1px solid rgba(118,185,0,0.2);
  border-radius:5px; padding:18px 20px; }
#panel-data .da-turn { display:grid; grid-template-columns:140px 1fr; gap:14px;
  align-items:start; }
#panel-data .da-role { color:#fff; font-size:11.5px; font-weight:700;
  text-transform:uppercase; letter-spacing:0.08em; padding-top:7px;
  text-align:right; }
#panel-data .da-role-tool { color:#e0a020; }
#panel-data .da-role-obs { color:#888; }
#panel-data .da-role-final { color:#76b900; }
#panel-data .da-msg { color:#ddd; font-size:13px; line-height:1.55;
  background:rgba(255,255,255,0.03); border-left:3px solid #555;
  padding:8px 14px; border-radius:0 3px 3px 0; }
#panel-data .da-msg code { color:#76b900; font-family:'SF Mono',monospace;
  background:rgba(118,185,0,0.1); padding:1px 5px; border-radius:2px;
  font-size:12px; }
#panel-data .da-msg-tool { background:rgba(224,160,32,0.06);
  border-left-color:#e0a020; color:#ddd;
  font-family:'SF Mono',Menlo,Consolas,monospace; font-size:12.5px;
  white-space:pre-line; }
#panel-data .da-msg-obs { background:rgba(128,128,128,0.08);
  border-left-color:#888; color:#aaa; font-style:italic; }
#panel-data .da-msg-final { background:rgba(118,185,0,0.1);
  border-left-color:#76b900; color:#fff; font-weight:500; }
#panel-risk .tl-caption { color:#888; font-size:12.5px; margin-top:12px;
  font-style:italic; text-align:center; }
#panel-risk .ra-two { display:grid; grid-template-columns:1.1fr 1fr;
  gap:28px; align-items:start; }
#panel-risk .ra-template { background:rgba(118,185,0,0.04);
  border:1px solid rgba(118,185,0,0.35); border-radius:4px;
  padding:18px 20px; }
#panel-risk .ra-t-label { color:#888; font-size:11px; font-weight:700;
  letter-spacing:0.14em; text-transform:uppercase; margin-bottom:10px; }
#panel-risk .ra-t-row { display:grid; grid-template-columns:1fr auto;
  gap:14px; align-items:center; margin-bottom:8px; }
#panel-risk .ra-t-head { color:#fff; font-size:14px; font-weight:700; }
#panel-risk .ra-t-impact { color:#bbb; font-size:12.5px; line-height:1.55;
  margin-bottom:4px; }
#panel-risk .ra-t-src { color:#76b900; font-size:11.5px;
  font-family:'SF Mono',Menlo,Consolas,monospace; }
#panel-risk .ra-ph { color:rgba(118,185,0,0.5); font-style:italic; }
#panel-risk .ra-legend { display:flex; flex-direction:column; gap:14px;
  background:rgba(0,0,0,0.2); border:1px solid rgba(118,185,0,0.2);
  border-radius:5px; padding:20px 22px; }
#panel-risk .ra-leg-row { display:grid; grid-template-columns:90px 1fr;
  gap:14px; align-items:center; }
#panel-risk .ra-chip { display:inline-block; padding:6px 0; border-radius:3px;
  font-size:12.5px; font-weight:700; letter-spacing:0.12em;
  font-family:'SF Mono',Menlo,Consolas,monospace; text-align:center;
  text-transform:uppercase; }
#panel-risk .ra-chip.h { background:rgba(192,64,64,0.15);
  border:1.5px solid #c04040; color:#c04040; }
#panel-risk .ra-chip.m { background:rgba(224,160,32,0.15);
  border:1.5px solid #e0a020; color:#e0a020; }
#panel-risk .ra-chip.l { background:rgba(118,185,0,0.15);
  border:1.5px solid #76b900; color:#76b900; }
#panel-risk .ra-leg-desc { color:#bbb; font-size:12.5px; line-height:1.5; }
#panel-risk .ra-findings { display:flex; flex-direction:column; gap:4px;
  background:rgba(0,0,0,0.2); border:1px solid rgba(118,185,0,0.2);
  border-radius:5px; padding:18px 22px; }
#panel-risk .ra-finding { display:grid; grid-template-columns:92px 1fr;
  gap:16px; align-items:start; padding:14px 0;
  border-top:1px dashed rgba(118,185,0,0.18); }
#panel-risk .ra-finding:first-of-type { border-top:none; padding-top:4px; }
#panel-risk .ra-hl { color:#fff; font-size:14px; font-weight:700;
  margin-bottom:5px; }
#panel-risk .ra-impact { color:#bbb; font-size:12.5px; line-height:1.55;
  margin-bottom:4px; }
#panel-risk .ra-source { color:#76b900; font-size:11.5px;
  font-family:'SF Mono',Menlo,Consolas,monospace; opacity:0.85; }
#panel-risk .ra-overall { margin-top:16px; padding:14px 18px;
  background:rgba(118,185,0,0.08); border-left:3px solid #76b900;
  border-radius:0 3px 3px 0; color:#ddd; font-size:13px;
  line-height:1.6; font-style:italic; }
#panel-risk .ra-overall strong { color:#fff; font-style:normal;
  font-weight:700; }
#panel-lp .tl-caption, #panel-chart .tl-caption { color:#888; font-size:12.5px;
  margin-top:12px; font-style:italic; text-align:center; }
#panel-lp .lp-formula { background:rgba(118,185,0,0.06);
  border:1px solid rgba(118,185,0,0.4); border-radius:5px;
  padding:28px 24px; text-align:center; margin-bottom:18px; }
#panel-lp .lp-obj { color:#fff; font-size:22px; font-weight:600;
  font-family:'SF Mono',Menlo,Consolas,monospace; line-height:1.8;
  letter-spacing:0.01em; }
#panel-lp .lp-t-cost { color:#76b900; }
#panel-lp .lp-t-risk { color:#e0a020; }
#panel-lp .lp-t-urg { color:#c04040; }
#panel-lp .lp-t-x { color:#4a9eff; }
#panel-lp .lp-legend { display:grid; grid-template-columns:1fr 1fr;
  gap:10px 22px; margin-top:6px; }
#panel-lp .lp-leg-row { display:flex; align-items:baseline; gap:10px; }
#panel-lp .lp-leg-k { font-family:'SF Mono',monospace; font-size:14px;
  font-weight:700; min-width:90px; }
#panel-lp .lp-leg-v { color:#bbb; font-size:12.5px; line-height:1.5; }
#panel-lp .lp-constr { display:grid; grid-template-columns:1fr 1fr 1fr;
  gap:16px; align-items:start; }
#panel-lp .lp-c-col { background:rgba(118,185,0,0.04);
  border:1px solid rgba(118,185,0,0.35); border-radius:4px;
  padding:18px 20px; }
#panel-lp .lp-c-h { color:#fff; font-size:13px; font-weight:700;
  letter-spacing:0.1em; text-transform:uppercase; margin-bottom:12px;
  display:flex; align-items:center; justify-content:space-between; }
#panel-lp .lp-c-tag { font-size:10px; font-weight:700; letter-spacing:0.08em;
  padding:3px 9px; border-radius:10px; font-family:'SF Mono',monospace; }
#panel-lp .lp-c-tag.lin { color:#76b900; background:rgba(118,185,0,0.15);
  border:1px solid #76b900; }
#panel-lp .lp-c-tag.mip { color:#e0a020; background:rgba(224,160,32,0.15);
  border:1px solid #e0a020; }
#panel-lp .lp-c-tag.flt { color:#888; background:rgba(128,128,128,0.12);
  border:1px solid #888; }
#panel-lp .lp-c-item { padding:10px 0; border-top:1px dashed rgba(118,185,0,0.18); }
#panel-lp .lp-c-item:first-of-type { border-top:none; padding-top:4px; }
#panel-lp .lp-c-name { color:#76b900; font-size:12.5px; font-weight:700;
  font-family:'SF Mono',monospace; margin-bottom:5px; }
#panel-lp .lp-c-desc { color:#bbb; font-size:12px; line-height:1.55; }
#panel-chart .ch-flow { display:grid; grid-template-columns:1fr 1fr;
  gap:12px; align-items:stretch; }
#panel-chart .ch-col { display:flex; flex-direction:column;
  background:rgba(118,185,0,0.04); border:1px solid rgba(118,185,0,0.35);
  border-radius:5px; padding:18px 20px; }
#panel-chart .ch-h { color:#fff; font-size:15px; font-weight:700;
  letter-spacing:0.1em; text-transform:uppercase; margin-bottom:14px;
  display:flex; align-items:center; justify-content:space-between; }
#panel-chart .ch-n { color:#76b900; font-size:12px; font-weight:700;
  background:rgba(118,185,0,0.15); border:1px solid #76b900;
  padding:2px 10px; border-radius:10px; letter-spacing:normal; }
#panel-chart .ch-list { list-style:none; padding:0; margin:0;
  display:flex; flex-direction:column; gap:5px; }
#panel-chart .ch-list li { display:flex; align-items:center; gap:12px;
  padding:10px 12px; border-radius:3px; cursor:help;
  transition:background 0.15s; }
#panel-chart .ch-list li:hover { background:rgba(118,185,0,0.1); }
#panel-chart .ch-icon { color:#76b900; font-size:16px;
  opacity:0.7; min-width:22px; text-align:center; }
#panel-chart .ch-name { color:#fff; font-size:14px; font-weight:500;
  font-family:'SF Mono',Menlo,Consolas,monospace; }
</style></head><body>
<canvas id="c"></canvas>
<div id="tip"></div>
<div id="panel">
  <div class="pclose" onclick="closePanel()">\u2715</div>
  <div class="ph">Pipeline Agent \u2014 Fast-Path Dispatcher</div>
  <div class="psub">Zero LLM in loop \u00b7 deterministic Python dispatch \u00b7 ~0.2s per tool \u00b7 output already structured (skips synthesizer)</div>

  <div class="gsec">
    <div class="gsec-n">Section 01</div>
    <div class="gsec-t">Dispatch Flow \u2014 Orchestrator Thinks, Pipeline Agent Executes</div>
    <svg class="fan-svg" viewBox="0 0 900 380" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <marker id="arrGp" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L7,4 L0,8 Z" fill="#76b900"/>
        </marker>
        <marker id="arrGpF" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L7,4 L0,8 Z" fill="#76b900" fill-opacity="0.5"/>
        </marker>
      </defs>

      <!-- Upstream label -->
      <text x="20" y="22" fill="#666" font-family="Inter,sans-serif" font-size="10" font-weight="700" letter-spacing="0.15em">UPSTREAM \u00b7 SHARED BY ALL AGENTS</text>
      <line x1="300" y1="18" x2="880" y2="18" stroke="rgba(118,185,0,0.2)" stroke-width="1"/>

      <!-- Row 1: upstream (faded) -->
      <g opacity="0.8">
        <rect x="30" y="40" width="140" height="46" rx="3" fill="rgba(255,255,255,0.04)" stroke="#555"/>
        <text x="100" y="68" text-anchor="middle" fill="#bbb" font-family="Inter,sans-serif" font-size="13" font-style="italic">user query</text>
        <line x1="170" y1="63" x2="204" y2="63" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGpF)" opacity="0.7"/>
        <rect x="210" y="40" width="190" height="46" rx="3" fill="rgba(118,185,0,0.04)" stroke="rgba(118,185,0,0.55)"/>
        <text x="305" y="62" text-anchor="middle" fill="#ddd" font-family="Inter,sans-serif" font-size="13" font-weight="600">Orchestrator</text>
        <text x="305" y="78" text-anchor="middle" fill="#888" font-family="SF Mono,monospace" font-size="10">picks tool + params</text>
        <line x1="400" y1="63" x2="434" y2="63" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGpF)" opacity="0.7"/>
        <rect x="440" y="40" width="140" height="46" rx="3" fill="rgba(118,185,0,0.08)" stroke="rgba(118,185,0,0.75)"/>
        <text x="510" y="62" text-anchor="middle" fill="#ddd" font-family="Inter,sans-serif" font-size="13" font-weight="600">Plan</text>
        <text x="510" y="78" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="10">user-approved \u2713</text>
      </g>

      <!-- Connector: Plan \u2192 Tool+params card -->
      <path d="M 510 86 C 510 140, 130 130, 130 174" stroke="#76b900" stroke-width="1.5" fill="none" marker-end="url(#arrGp)"/>

      <!-- Row 2 label -->
      <text x="20" y="162" fill="#76b900" font-family="Inter,sans-serif" font-size="10.5" font-weight="700" letter-spacing="0.15em">PIPELINE AGENT \u00b7 FAST PATH</text>
      <line x1="230" y1="158" x2="880" y2="158" stroke="rgba(118,185,0,0.35)" stroke-width="1"/>

      <!-- Tool+params input card -->
      <rect x="30" y="178" width="200" height="80" rx="4" fill="rgba(118,185,0,0.04)" stroke="rgba(118,185,0,0.55)"/>
      <text x="130" y="200" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="10.5" font-weight="700" letter-spacing="0.12em">TOOL + PARAMS</text>
      <text x="130" y="222" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="11.5">query_forecast_summary</text>
      <text x="130" y="242" text-anchor="middle" fill="#888" font-family="SF Mono,monospace" font-size="10.5">{ forecast_run_id: 0 }</text>

      <line x1="230" y1="218" x2="264" y2="218" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGp)"/>

      <!-- DISPATCH box (prominent) -->
      <rect x="270" y="168" width="280" height="100" rx="4" fill="rgba(118,185,0,0.15)" stroke="#76b900" stroke-width="2.5"/>
      <text x="410" y="196" text-anchor="middle" fill="#fff" font-family="Inter,sans-serif" font-size="17" font-weight="700">\u2699 DISPATCH</text>
      <text x="410" y="220" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="12.5">DIRECT_PIPELINE_TOOLS[name]</text>
      <text x="410" y="240" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="12.5">(**params)</text>
      <text x="410" y="258" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="10.5">direct Python call \u00b7 ~0.2s</text>

      <!-- ZERO LLM IN LOOP banner -->
      <rect x="290" y="280" width="240" height="26" rx="3" fill="rgba(224,160,32,0.1)" stroke="#e0a020" stroke-width="1"/>
      <text x="410" y="297" text-anchor="middle" fill="#e0a020" font-family="Inter,sans-serif" font-size="11.5" font-weight="700" letter-spacing="0.14em">\u26A1 ZERO LLM IN LOOP</text>

      <line x1="550" y1="218" x2="584" y2="218" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGp)"/>

      <!-- Structured Result -->
      <rect x="590" y="178" width="170" height="80" rx="4" fill="rgba(118,185,0,0.12)" stroke="#76b900" stroke-width="1.8"/>
      <text x="675" y="202" text-anchor="middle" fill="#fff" font-family="Inter,sans-serif" font-size="14" font-weight="700">Structured Result</text>
      <text x="675" y="224" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="10.5">table \u00b7 chart \u00b7 JSON</text>
      <text x="675" y="244" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="10">no LLM summary needed</text>

      <!-- Result \u2192 Synthesizer (blocked, red dashed with \u2717) -->
      <line x1="760" y1="218" x2="794" y2="218" stroke="rgba(192,64,64,0.6)" stroke-width="1.5" stroke-dasharray="4 3"/>
      <text x="777" y="211" text-anchor="middle" fill="#c04040" font-family="Inter,sans-serif" font-size="14" font-weight="700">\u2717</text>

      <!-- Synthesizer (dim + strikethrough) -->
      <g opacity="0.55">
        <rect x="800" y="188" width="95" height="60" rx="4" fill="rgba(128,128,128,0.08)" stroke="rgba(128,128,128,0.6)" stroke-width="1.2" stroke-dasharray="4 3"/>
        <text x="848" y="214" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="11.5" font-weight="600">Synthesizer</text>
        <text x="848" y="232" text-anchor="middle" fill="#c04040" font-family="Inter,sans-serif" font-size="10" font-weight="700" letter-spacing="0.12em">SKIPPED</text>
        <line x1="803" y1="216" x2="892" y2="216" stroke="#c04040" stroke-width="1.2" opacity="0.7"/>
      </g>

      <!-- caption -->
      <text x="450" y="352" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="12">Orchestrator does the thinking \u00b7 Pipeline Agent just executes \u00b7 output is already structured, so synthesizer is bypassed</text>
    </svg>
  </div>

  <div class="gsec">
    <div class="gsec-n">Section 02</div>
    <div class="gsec-t">Toolset \u2014 10 Tools Across 3 Pipeline Layers <span style="color:#888; font-weight:400; font-size:13px; margin-left:12px;">hover any tool for details</span></div>

    <div class="pla-flow">
    <div class="pla-col">
      <div class="pla-h">Forecast Layer <span class="pla-n">3</span></div>
      <div class="pla-inner">
        <ul class="pla-list">
          <li title="Production demand forecast overview \u2014 total units, facilities, SKUs, horizon weeks."><span class="pla-num">01</span><span class="pla-name">query_forecast_summary</span></li>
          <li title="Week \u00d7 facility \u00d7 SKU forecast with 90% confidence intervals; supports CSV export."><span class="pla-num">02</span><span class="pla-name">query_forecast_drilldown</span></li>
          <li title="Model explainability: validation metrics, feature importance, or baseline comparison."><span class="pla-num">03</span><span class="pla-name">query_forecast_model_assessment</span></li>
        </ul>
        <div class="pla-sql-side">
          <div class="pla-vlabel">SQL sources</div>
          <div class="pla-views">
            <div class="pla-view">fact_semiconductor_demand_forecast</div>
            <div class="pla-view">dim_forecast_run</div>
          </div>
        </div>
      </div>
    </div>

    <div class="pla-arr">\u2193</div>

    <div class="pla-col">
      <div class="pla-h">BOM Layer <span class="pla-n">2</span></div>
      <div class="pla-inner">
        <ul class="pla-list">
          <li title="BOM-exploded gross component demand across the full horizon, no inventory offset."><span class="pla-num">04</span><span class="pla-name">query_component_requirements</span></li>
          <li title="Single-SKU BOM explosion \u2014 how one finished good maps to procurement components."><span class="pla-num">05</span><span class="pla-name">query_bom_translation</span></li>
        </ul>
        <div class="pla-sql-side">
          <div class="pla-vlabel">SQL sources</div>
          <div class="pla-views">
            <div class="pla-view">vw_component_requirement_lp</div>
            <div class="pla-view">dim_bom</div>
          </div>
        </div>
      </div>
    </div>

    <div class="pla-arr">\u2193</div>

    <div class="pla-col">
      <div class="pla-h">Inventory Layer <span class="pla-n">5</span></div>
      <div class="pla-inner">
        <ul class="pla-list">
          <li title="Weekly inventory-adjusted procurement trigger signal (net requirement > 0)."><span class="pla-num">06</span><span class="pla-name">query_procurement_status</span></li>
          <li title="Combined summary: BOM gross demand + weekly trigger signal in one view."><span class="pla-num">07</span><span class="pla-name">query_procurement_planning_summary</span></li>
          <li title="Horizon-level LP demand floor per component \u2014 what the LP allocates against."><span class="pla-num">08</span><span class="pla-name">query_aggregated_procurement_need</span></li>
          <li title="Week \u00d7 component \u00d7 facility grain with rolling inventory depletion math (all rows)."><span class="pla-num">09</span><span class="pla-name">query_procurement_drilldown</span></li>
          <li title="Only the weeks/facilities where procurement is actually active (net_req > 0)."><span class="pla-num">10</span><span class="pla-name">query_triggered_procurement_rows</span></li>
        </ul>
        <div class="pla-sql-side">
          <div class="pla-vlabel">SQL sources</div>
          <div class="pla-views">
            <div class="pla-view">vw_procurement_requirement</div>
            <div class="pla-view">fact_inventory_policy</div>
            <div class="pla-view">fact_component_inventory_history</div>
          </div>
        </div>
      </div>
    </div>
  </div>
  </div>
</div>
<div id="panel-orch">
  <div class="pclose" onclick="closeOrchPanel()">\u2715</div>
  <div class="ph">Orchestrator \u2014 Hybrid Routing Engine</div>
  <div class="psub">LLM intent classification \u00b7 deterministic param extraction \u00b7 human-in-the-loop plan approval</div>

  <div class="gsec">
    <div class="gsec-n">Section 01</div>
    <div class="gsec-t">Intent Classification \u2014 Fan-out to 6 Agents</div>
    <svg class="fan-svg" viewBox="0 0 900 320" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <marker id="arrGreen" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L7,4 L0,8 Z" fill="#76b900"/>
        </marker>
      </defs>
      <!-- input prompt -->
      <rect x="340" y="10" width="220" height="40" rx="4" fill="rgba(255,255,255,0.04)" stroke="#555"/>
      <text x="450" y="35" text-anchor="middle" fill="#bbb" font-family="Inter,sans-serif" font-size="13" font-style="italic">"\u2026 user prompt \u2026"</text>
      <!-- arrow to LLM -->
      <line x1="450" y1="50" x2="450" y2="78" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGreen)"/>
      <!-- Claude LLM box -->
      <rect x="320" y="85" width="260" height="72" rx="5" fill="rgba(118,185,0,0.08)" stroke="#76b900" stroke-width="2"/>
      <text x="450" y="110" text-anchor="middle" fill="#fff" font-family="Inter,sans-serif" font-size="15" font-weight="700">LLM</text>
      <text x="450" y="132" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="11">structured output</text>
      <text x="450" y="148" text-anchor="middle" fill="#888" font-family="SF Mono,monospace" font-size="10.5">OrchestratorOutput { intent, tasks[] }</text>
      <!-- fan-out lines to 7 agents -->
      <g stroke="#76b900" stroke-width="1.2" fill="none" opacity="0.6">
        <path d="M 450 157 Q 450 190 80 215"/>
        <path d="M 450 157 Q 450 190 205 215"/>
        <path d="M 450 157 Q 450 190 330 215"/>
        <path d="M 450 157 L 455 215"/>
        <path d="M 450 157 Q 450 190 580 215"/>
        <path d="M 450 157 Q 450 190 705 215"/>
        <path d="M 450 157 Q 450 190 830 215"/>
      </g>
      <!-- 7 agent pills -->
      <g font-family="SF Mono,Menlo,Consolas,monospace" font-size="12" font-weight="600">
        <rect x="25" y="215" width="110" height="36" rx="3" fill="rgba(118,185,0,0.12)" stroke="#76b900" stroke-width="1.5"/>
        <text x="80" y="238" text-anchor="middle" fill="#76b900">pipeline_agent</text>
        <rect x="150" y="215" width="110" height="36" rx="3" fill="rgba(118,185,0,0.12)" stroke="#76b900" stroke-width="1.5"/>
        <text x="205" y="238" text-anchor="middle" fill="#76b900">lp_agent</text>
        <rect x="275" y="215" width="110" height="36" rx="3" fill="rgba(118,185,0,0.12)" stroke="#76b900" stroke-width="1.5"/>
        <text x="330" y="238" text-anchor="middle" fill="#76b900">chart_agent</text>
        <rect x="400" y="215" width="110" height="36" rx="3" fill="rgba(118,185,0,0.12)" stroke="#76b900" stroke-width="1.5"/>
        <text x="455" y="238" text-anchor="middle" fill="#76b900">data_agent</text>
        <rect x="525" y="215" width="110" height="36" rx="3" fill="rgba(118,185,0,0.12)" stroke="#76b900" stroke-width="1.5"/>
        <text x="580" y="238" text-anchor="middle" fill="#76b900">risk_agent</text>
        <rect x="650" y="215" width="110" height="36" rx="3" fill="rgba(118,185,0,0.12)" stroke="#76b900" stroke-width="1.5"/>
        <text x="705" y="238" text-anchor="middle" fill="#76b900">planner</text>
        <rect x="775" y="215" width="110" height="36" rx="3" fill="rgba(128,128,80,0.06)" stroke="#888" stroke-width="1.2" stroke-dasharray="4 3"/>
        <text x="830" y="238" text-anchor="middle" fill="#888">out_of_scope</text>
      </g>
      <!-- caption -->
      <text x="450" y="290" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="11.5">LLM emits structured tasks. Each carries <tspan fill="#76b900" font-family="SF Mono,monospace">agent</tspan> \u00b7 <tspan fill="#76b900" font-family="SF Mono,monospace">tool</tspan> \u00b7 <tspan fill="#76b900" font-family="SF Mono,monospace">params_json</tspan>.</text>
    </svg>
  </div>

  <div class="gsec">
    <div class="gsec-n">Section 02</div>
    <div class="gsec-t">Few-Shot Prompt \u2014 17+ Labeled Examples</div>
    <div class="ex-flow">
      <div class="ex-q">"plan procurement for semiconductors"</div>
      <div class="ex-arr">\u2192</div>
      <div class="ex-chip">planner</div>
    </div>
    <div class="ex-flow">
      <div class="ex-q">"transistors with moderate risk"</div>
      <div class="ex-arr">\u2192</div>
      <div class="ex-chip">lp_agent \u00b7 \u03bb=0.5</div>
    </div>
    <div class="ex-flow">
      <div class="ex-q">"what if SUP_HKG_38 unavailable?"</div>
      <div class="ex-arr">\u2192</div>
      <div class="ex-chip">lp_agent \u00b7 exclude</div>
    </div>
    <div class="ex-flow">
      <div class="ex-q">"rank the top suppliers"</div>
      <div class="ex-arr">\u2192</div>
      <div class="ex-chip">chart_agent</div>
    </div>
    <div class="ex-flow">
      <div class="ex-q">"what's the weather in Tokyo?"</div>
      <div class="ex-arr">\u2192</div>
      <div class="ex-chip" style="color:#888;border-color:#888;background:rgba(128,128,128,0.08);">out_of_scope</div>
    </div>
  </div>

  <div class="gsec">
    <div class="gsec-n">Section 03</div>
    <div class="gsec-t">Deterministic Param Extractor \u2014 Regex + Keyword Gates</div>
    <div class="pm-row">
      <div class="pm-field">lambda_risk</div>
      <div class="pm-in">"\u2026 with <mark>moderate</mark> risk"</div>
      <div class="pm-arr">\u2192</div>
      <div class="pm-out">0.5</div>
    </div>
    <div class="pm-row">
      <div class="pm-field">max_supplier_share</div>
      <div class="pm-in">"apply a <mark>40% cap</mark> per supplier"</div>
      <div class="pm-arr">\u2192</div>
      <div class="pm-out">0.40</div>
    </div>
    <div class="pm-row">
      <div class="pm-field">urgency</div>
      <div class="pm-in">"this is <mark>urgent</mark>"</div>
      <div class="pm-arr">\u2192</div>
      <div class="pm-out">true</div>
    </div>
    <div class="pm-row">
      <div class="pm-field">exclude_supplier_ids</div>
      <div class="pm-in">"exclude <mark>SUP_HKG_38</mark>"</div>
      <div class="pm-arr">\u2192</div>
      <div class="pm-out">[SUP_HKG_38]</div>
    </div>
    <div class="pm-row">
      <div class="pm-field">diversification_mode</div>
      <div class="pm-in">"spread <mark>across countries</mark>"</div>
      <div class="pm-arr">\u2192</div>
      <div class="pm-out">country_diversified</div>
    </div>
  </div>

  <div class="gsec">
    <div class="gsec-n">Section 04</div>
    <div class="gsec-t">Plan Approval \u2014 Human-in-the-Loop Gate</div>
    <svg class="fan-svg" viewBox="0 0 900 180" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <marker id="arrG2" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L7,4 L0,8 Z" fill="#76b900"/>
        </marker>
        <marker id="arrR" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L7,4 L0,8 Z" fill="#c04040"/>
        </marker>
      </defs>

      <!-- top row boxes -->
      <g font-family="SF Mono,Menlo,Consolas,monospace" font-size="13" font-weight="600">
        <rect x="30" y="20" width="90" height="40" rx="3" fill="rgba(118,185,0,0.06)" stroke="#76b900" stroke-width="1.5"/>
        <text x="75" y="45" text-anchor="middle" fill="#fff">LLM</text>

        <rect x="160" y="20" width="90" height="40" rx="3" fill="rgba(118,185,0,0.06)" stroke="#76b900" stroke-width="1.5"/>
        <text x="205" y="45" text-anchor="middle" fill="#fff">Plan</text>

        <rect x="290" y="20" width="150" height="40" rx="3" fill="rgba(224,160,32,0.08)" stroke="#e0a020" stroke-width="1.8"/>
        <text x="365" y="45" text-anchor="middle" fill="#e0a020">\u23F8 interrupt()</text>

        <rect x="560" y="20" width="130" height="40" rx="3" fill="rgba(118,185,0,0.15)" stroke="#76b900" stroke-width="1.5"/>
        <text x="625" y="45" text-anchor="middle" fill="#76b900">\u2713 Approve</text>

        <rect x="730" y="20" width="120" height="40" rx="3" fill="rgba(118,185,0,0.06)" stroke="#76b900" stroke-width="1.5"/>
        <text x="790" y="45" text-anchor="middle" fill="#fff">Execute</text>
      </g>

      <!-- horizontal arrows (green except around interrupt which branches) -->
      <g stroke-width="1.5" fill="none">
        <line x1="120" y1="40" x2="156" y2="40" stroke="#76b900" marker-end="url(#arrG2)"/>
        <line x1="250" y1="40" x2="286" y2="40" stroke="#76b900" marker-end="url(#arrG2)"/>
        <line x1="440" y1="40" x2="556" y2="40" stroke="#76b900" marker-end="url(#arrG2)"/>
        <line x1="690" y1="40" x2="726" y2="40" stroke="#76b900" marker-end="url(#arrG2)"/>
      </g>

      <!-- label above Approve arrow -->
      <text x="498" y="32" text-anchor="middle" fill="#76b900" font-family="Inter,sans-serif" font-size="11" font-weight="600">user approves</text>

      <!-- reject branch: down from interrupt() bottom, right to Reject box -->
      <g stroke="#c04040" stroke-width="1.5" fill="none">
        <path d="M 365 60 L 365 110" marker-end="url(#arrR)"/>
      </g>
      <!-- label next to reject arrow -->
      <text x="378" y="88" fill="#c04040" font-family="Inter,sans-serif" font-size="11" font-weight="600">user rejects</text>

      <!-- Reject box -->
      <g font-family="SF Mono,Menlo,Consolas,monospace" font-size="13" font-weight="600">
        <rect x="295" y="115" width="140" height="40" rx="3" fill="rgba(192,64,64,0.1)" stroke="#c04040" stroke-width="1.5"/>
        <text x="365" y="140" text-anchor="middle" fill="#c04040">\u2717 Reject</text>
      </g>

      <!-- arrow from Reject to caption -->
      <g stroke="#c04040" stroke-width="1.5" fill="none">
        <line x1="435" y1="135" x2="475" y2="135" marker-end="url(#arrR)"/>
      </g>
      <text x="485" y="140" fill="#888" font-family="Inter,sans-serif" font-size="13" font-style="italic">back to user \u2014 no agents run</text>
    </svg>
    <div class="tl-caption">Execution pauses at <code style="color:#76b900;font-family:'SF Mono',monospace;">interrupt()</code> until the user responds. Only approved plans touch downstream agents; rejected plans are discarded before any SQL / LP / web-search runs.</div>
  </div>
</div>
<div id="panel-data">
  <div class="pclose" onclick="closeDataPanel()">\u2715</div>
  <div class="ph">Data Agent \u2014 ReAct SQL Explorer</div>
  <div class="psub">LLM-driven iterative SQL via postgres MCP \u00b7 free-form exploration \u00b7 ~5s / up to 3 iterations</div>

  <div class="gsec">
    <div class="gsec-n">Section 01</div>
    <div class="gsec-t">ReAct Loop \u2014 Think \u00b7 Act \u00b7 Observe</div>
    <svg class="fan-svg" viewBox="0 0 900 390" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <marker id="arrGd" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L7,4 L0,8 Z" fill="#76b900"/>
        </marker>
        <marker id="arrGdF" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L7,4 L0,8 Z" fill="#76b900" fill-opacity="0.5"/>
        </marker>
        <marker id="arrOd" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L7,4 L0,8 Z" fill="#e0a020"/>
        </marker>
      </defs>

      <!-- Upstream label -->
      <text x="20" y="22" fill="#666" font-family="Inter,sans-serif" font-size="10" font-weight="700" letter-spacing="0.15em">UPSTREAM \u00b7 SHARED BY ALL AGENTS</text>
      <line x1="300" y1="18" x2="880" y2="18" stroke="rgba(118,185,0,0.2)" stroke-width="1"/>

      <!-- Row 1: upstream context (faded) -->
      <g opacity="0.8">
        <rect x="30" y="40" width="140" height="46" rx="3" fill="rgba(255,255,255,0.04)" stroke="#555"/>
        <text x="100" y="68" text-anchor="middle" fill="#bbb" font-family="Inter,sans-serif" font-size="13" font-style="italic">user query</text>

        <line x1="170" y1="63" x2="204" y2="63" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGdF)" opacity="0.7"/>

        <rect x="210" y="40" width="190" height="46" rx="3" fill="rgba(118,185,0,0.04)" stroke="rgba(118,185,0,0.55)"/>
        <text x="305" y="62" text-anchor="middle" fill="#ddd" font-family="Inter,sans-serif" font-size="13" font-weight="600">Orchestrator</text>
        <text x="305" y="78" text-anchor="middle" fill="#888" font-family="SF Mono,monospace" font-size="10">classify + extract</text>

        <line x1="400" y1="63" x2="434" y2="63" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGdF)" opacity="0.7"/>

        <rect x="440" y="40" width="140" height="46" rx="3" fill="rgba(118,185,0,0.08)" stroke="rgba(118,185,0,0.75)"/>
        <text x="510" y="62" text-anchor="middle" fill="#ddd" font-family="Inter,sans-serif" font-size="13" font-weight="600">Plan</text>
        <text x="510" y="78" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="10">user-approved \u2713</text>
      </g>

      <!-- Connector: Plan bottom \u2192 LLM top -->
      <path d="M 510 86 C 510 140, 250 120, 250 176" stroke="#76b900" stroke-width="1.5" fill="none" marker-end="url(#arrGd)"/>

      <!-- Row 2 label -->
      <text x="20" y="162" fill="#76b900" font-family="Inter,sans-serif" font-size="10.5" font-weight="700" letter-spacing="0.15em">DATA AGENT</text>
      <line x1="115" y1="158" x2="880" y2="158" stroke="rgba(118,185,0,0.35)" stroke-width="1"/>

      <!-- Row 2: LLM (ReAct) -->
      <rect x="140" y="180" width="220" height="88" rx="4" fill="rgba(118,185,0,0.08)" stroke="#76b900" stroke-width="2"/>
      <text x="250" y="210" text-anchor="middle" fill="#fff" font-family="Inter,sans-serif" font-size="16" font-weight="700">LLM (ReAct)</text>
      <text x="250" y="232" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="12">think \u00b7 decide</text>
      <text x="250" y="250" text-anchor="middle" fill="#888" font-family="SF Mono,monospace" font-size="11">tool_call  or  final</text>

      <!-- arrow LLM \u2192 Final answer -->
      <line x1="360" y1="212" x2="494" y2="212" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGd)"/>
      <text x="427" y="202" text-anchor="middle" fill="#76b900" font-family="Inter,sans-serif" font-size="11" font-weight="600">final answer</text>

      <!-- Final answer box -->
      <rect x="500" y="188" width="170" height="48" rx="4" fill="rgba(118,185,0,0.15)" stroke="#76b900" stroke-width="1.8"/>
      <text x="585" y="218" text-anchor="middle" fill="#fff" font-family="Inter,sans-serif" font-size="14" font-weight="700">Final Answer</text>

      <!-- dashed arrow \u2192 Synthesizer -->
      <line x1="670" y1="212" x2="704" y2="212" stroke="rgba(118,185,0,0.5)" stroke-width="1.5" stroke-dasharray="4 3" marker-end="url(#arrGdF)"/>

      <!-- Synthesizer (dashed, dim) -->
      <rect x="710" y="188" width="170" height="48" rx="4" fill="rgba(118,185,0,0.03)" stroke="rgba(118,185,0,0.4)" stroke-width="1.2" stroke-dasharray="4 3"/>
      <text x="795" y="212" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="13" font-weight="600">Synthesizer</text>
      <text x="795" y="228" text-anchor="middle" fill="#666" font-family="Inter,sans-serif" font-size="10">downstream</text>

      <!-- arrow LLM down \u2192 execute_sql -->
      <path d="M 250 268 L 250 302" stroke="#e0a020" stroke-width="1.5" fill="none" marker-end="url(#arrOd)"/>
      <text x="265" y="290" fill="#e0a020" font-family="Inter,sans-serif" font-size="11" font-weight="600">tool_call</text>

      <!-- execute_sql box -->
      <rect x="160" y="306" width="180" height="52" rx="4" fill="rgba(224,160,32,0.08)" stroke="#e0a020" stroke-width="1.8"/>
      <text x="250" y="330" text-anchor="middle" fill="#e0a020" font-family="SF Mono,monospace" font-size="14" font-weight="700">execute_sql(\u2026)</text>
      <text x="250" y="348" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="10.5">via postgres MCP</text>

      <!-- loop back execute_sql \u2192 LLM (observation) -->
      <path d="M 160 332 C 90 332, 90 212, 134 212" stroke="#e0a020" stroke-width="1.5" fill="none" marker-end="url(#arrOd)"/>
      <text x="60" y="285" fill="#e0a020" font-family="Inter,sans-serif" font-size="11" font-weight="600">observation</text>

      <!-- caption -->
      <text x="450" y="380" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="12">Orchestrator classifies intent \u00b7 user approves Plan \u00b7 Data Agent iterates SQL + LLM up to ~3 times</text>
    </svg>
  </div>

  <div class="gsec">
    <div class="gsec-n">Section 02</div>
    <div class="gsec-t">Toolset + Accessible Schema</div>
    <div class="da-two">
      <div>
        <div class="da-h-small">MCP Tools</div>
        <div class="da-tool">
          <div class="da-tool-name">execute_sql(query)</div>
          <div class="da-tool-desc">Runs an arbitrary SELECT against the whitelisted views. The primary tool for every data lookup.</div>
        </div>
        <div class="da-tool">
          <div class="da-tool-name">list_tables()</div>
          <div class="da-tool-desc">Schema introspection helper \u2014 the agent can inspect available columns when the prompt context isn\u2019t enough.</div>
        </div>
      </div>
      <div>
        <div class="da-h-small">Accessible Schema (whitelisted)</div>
        <div class="da-schema-group">
          <div class="da-gk">Supplier</div>
          <div class="da-gv">
            <span class="da-chip">vw_supplier_complete_profile</span>
            <span class="da-chip">dim_supplier</span>
            <span class="da-chip">fact_supplier_product_profile</span>
          </div>
        </div>
        <div class="da-schema-group">
          <div class="da-gk">Forecast</div>
          <div class="da-gv">
            <span class="da-chip">fact_semiconductor_demand_forecast</span>
            <span class="da-chip">dim_forecast_run</span>
          </div>
        </div>
        <div class="da-schema-group">
          <div class="da-gk">BOM / Component</div>
          <div class="da-gv">
            <span class="da-chip">vw_component_requirement_lp</span>
            <span class="da-chip">dim_bom</span>
            <span class="da-chip">dim_product</span>
          </div>
        </div>
        <div class="da-schema-group">
          <div class="da-gk">Inventory</div>
          <div class="da-gv">
            <span class="da-chip">vw_procurement_requirement</span>
            <span class="da-chip">fact_inventory_policy</span>
            <span class="da-chip">fact_component_inventory_history</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="gsec">
    <div class="gsec-n">Section 03</div>
    <div class="gsec-t">Example Trace \u2014 \u201CWhich Korean suppliers have the lowest disruption risk?\u201D</div>
    <div class="da-trace">
      <div class="da-turn">
        <div class="da-role">LLM \u00b7 thought</div>
        <div class="da-msg">I\u2019ll query <code>vw_supplier_complete_profile</code>, filter by <code>country_code='KOR'</code>, and order by disruption probability ascending.</div>
      </div>
      <div class="da-turn">
        <div class="da-role da-role-tool">tool \u00b7 execute_sql</div>
        <div class="da-msg da-msg-tool">SELECT supplier_id, disruption_probability
FROM vw_supplier_complete_profile
WHERE country_code = 'KOR'
ORDER BY disruption_probability ASC;</div>
      </div>
      <div class="da-turn">
        <div class="da-role da-role-obs">observation</div>
        <div class="da-msg da-msg-obs">3 rows returned \u2014 SUP_KOR_02 (0.08) \u00b7 SUP_KOR_15 (0.11) \u00b7 SUP_KOR_22 (0.19)</div>
      </div>
      <div class="da-turn">
        <div class="da-role da-role-final">LLM \u00b7 final</div>
        <div class="da-msg da-msg-final">SUP_KOR_02 has the lowest disruption probability at 8%, followed by SUP_KOR_15 at 11% and SUP_KOR_22 at 19%.</div>
      </div>
    </div>
    <div class="tl-caption">1 tool call \u00b7 2 LLM turns \u00b7 typical shape for a supplier lookup</div>
  </div>
</div>
<div id="panel-risk">
  <div class="pclose" onclick="closeRiskPanel()">\u2715</div>
  <div class="ph">Risk Agent \u2014 Geopolitical News Scanner</div>
  <div class="psub">Tavily web search \u00b7 30-day window \u00b7 single call \u00b7 HIGH / MED / LOW labeled findings with sources</div>

  <div class="gsec">
    <div class="gsec-n">Section 01</div>
    <div class="gsec-t">Pipeline \u2014 Search \u00b7 Score \u00b7 Cite</div>
    <svg class="fan-svg" viewBox="0 0 900 330" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <marker id="arrGr" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L7,4 L0,8 Z" fill="#76b900"/>
        </marker>
        <marker id="arrGrF" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L7,4 L0,8 Z" fill="#76b900" fill-opacity="0.5"/>
        </marker>
      </defs>

      <!-- Upstream label -->
      <text x="20" y="22" fill="#666" font-family="Inter,sans-serif" font-size="10" font-weight="700" letter-spacing="0.15em">UPSTREAM \u00b7 SHARED BY ALL AGENTS</text>
      <line x1="300" y1="18" x2="880" y2="18" stroke="rgba(118,185,0,0.2)" stroke-width="1"/>

      <!-- Row 1: upstream context (faded) -->
      <g opacity="0.8">
        <rect x="30" y="40" width="140" height="46" rx="3" fill="rgba(255,255,255,0.04)" stroke="#555"/>
        <text x="100" y="68" text-anchor="middle" fill="#bbb" font-family="Inter,sans-serif" font-size="13" font-style="italic">user query</text>

        <line x1="170" y1="63" x2="204" y2="63" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGrF)" opacity="0.7"/>

        <rect x="210" y="40" width="190" height="46" rx="3" fill="rgba(118,185,0,0.04)" stroke="rgba(118,185,0,0.55)"/>
        <text x="305" y="62" text-anchor="middle" fill="#ddd" font-family="Inter,sans-serif" font-size="13" font-weight="600">Orchestrator</text>
        <text x="305" y="78" text-anchor="middle" fill="#888" font-family="SF Mono,monospace" font-size="10">classify + extract</text>

        <line x1="400" y1="63" x2="434" y2="63" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGrF)" opacity="0.7"/>

        <rect x="440" y="40" width="140" height="46" rx="3" fill="rgba(118,185,0,0.08)" stroke="rgba(118,185,0,0.75)"/>
        <text x="510" y="62" text-anchor="middle" fill="#ddd" font-family="Inter,sans-serif" font-size="13" font-weight="600">Plan</text>
        <text x="510" y="78" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="10">user-approved \u2713</text>
      </g>

      <!-- Connector: Plan bottom \u2192 Tavily top -->
      <path d="M 510 86 C 510 132, 145 118, 145 170" stroke="#76b900" stroke-width="1.5" fill="none" marker-end="url(#arrGr)"/>

      <!-- Row 2 label -->
      <text x="20" y="154" fill="#76b900" font-family="Inter,sans-serif" font-size="10.5" font-weight="700" letter-spacing="0.15em">RISK AGENT</text>
      <line x1="115" y1="150" x2="880" y2="150" stroke="rgba(118,185,0,0.35)" stroke-width="1"/>

      <!-- Row 2: Tavily (orange, external) -->
      <rect x="35" y="172" width="220" height="82" rx="4" fill="rgba(224,160,32,0.08)" stroke="#e0a020" stroke-width="2"/>
      <text x="145" y="203" text-anchor="middle" fill="#e0a020" font-family="SF Mono,monospace" font-size="14" font-weight="700">tavily_news_search</text>
      <text x="145" y="223" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="11">5\u20138 word query \u00b7 days=30</text>
      <text x="145" y="241" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="10.5">external web \u00b7 single call</text>

      <line x1="255" y1="213" x2="289" y2="213" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGr)"/>

      <!-- Analysis -->
      <rect x="295" y="172" width="190" height="82" rx="4" fill="rgba(118,185,0,0.08)" stroke="#76b900" stroke-width="2"/>
      <text x="390" y="203" text-anchor="middle" fill="#fff" font-family="Inter,sans-serif" font-size="14" font-weight="700">LLM analysis</text>
      <text x="390" y="223" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="11">score \u00b7 cite \u00b7 format</text>
      <text x="390" y="241" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="10.5">max 5 findings \u00b7 &lt;200 words</text>

      <line x1="485" y1="213" x2="519" y2="213" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGr)"/>

      <!-- Findings -->
      <rect x="525" y="172" width="160" height="82" rx="4" fill="rgba(118,185,0,0.12)" stroke="#76b900" stroke-width="1.8"/>
      <text x="605" y="200" text-anchor="middle" fill="#fff" font-family="Inter,sans-serif" font-size="14" font-weight="700">Findings</text>
      <g font-family="SF Mono,monospace" font-size="10.5" font-weight="700">
        <rect x="537" y="212" width="42" height="16" rx="2" fill="rgba(192,64,64,0.18)" stroke="#c04040" stroke-width="1"/>
        <text x="558" y="223" text-anchor="middle" fill="#c04040">HIGH</text>
        <rect x="584" y="212" width="36" height="16" rx="2" fill="rgba(224,160,32,0.18)" stroke="#e0a020" stroke-width="1"/>
        <text x="602" y="223" text-anchor="middle" fill="#e0a020">MED</text>
        <rect x="625" y="212" width="34" height="16" rx="2" fill="rgba(118,185,0,0.18)" stroke="#76b900" stroke-width="1"/>
        <text x="642" y="223" text-anchor="middle" fill="#76b900">LOW</text>
      </g>
      <text x="605" y="244" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="10">+ source URLs</text>

      <!-- dashed arrow \u2192 Synthesizer -->
      <line x1="685" y1="213" x2="719" y2="213" stroke="rgba(118,185,0,0.5)" stroke-width="1.5" stroke-dasharray="4 3" marker-end="url(#arrGrF)"/>

      <!-- Synthesizer (dashed, dim) -->
      <rect x="725" y="184" width="150" height="60" rx="4" fill="rgba(118,185,0,0.03)" stroke="rgba(118,185,0,0.4)" stroke-width="1.2" stroke-dasharray="4 3"/>
      <text x="800" y="210" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="12" font-weight="600">Synthesizer</text>
      <text x="800" y="228" text-anchor="middle" fill="#666" font-family="Inter,sans-serif" font-size="10">downstream</text>

      <!-- caption -->
      <text x="450" y="300" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="12">Orchestrator classifies intent \u00b7 user approves Plan \u00b7 Risk Agent performs one focused search</text>
    </svg>
  </div>

  <div class="gsec">
    <div class="gsec-n">Section 02</div>
    <div class="gsec-t">Output Anatomy \u2014 Every Finding Has the Same Shape</div>
    <div class="ra-two">
      <div class="ra-template">
        <div class="ra-t-label">Template (per finding)</div>
        <div class="ra-t-row">
          <div class="ra-t-head"><span class="ra-ph">**Headline**</span></div>
          <div class="ra-chip h" style="padding:5px 12px;">RISK: LEVEL</div>
        </div>
        <div class="ra-t-impact"><span class="ra-ph">one-sentence impact statement describing the supply-chain consequence</span></div>
        <div class="ra-t-src"><span class="ra-ph">[source](https://\u2026)</span></div>
      </div>
      <div class="ra-legend">
        <div class="ra-leg-row">
          <div class="ra-chip h">HIGH</div>
          <div class="ra-leg-desc">Critical disruption \u2014 active or imminent supply impact</div>
        </div>
        <div class="ra-leg-row">
          <div class="ra-chip m">MED</div>
          <div class="ra-leg-desc">Moderate concern \u2014 policy signal or regional tension worth tracking</div>
        </div>
        <div class="ra-leg-row">
          <div class="ra-chip l">LOW</div>
          <div class="ra-leg-desc">Monitor \u2014 contextual / stabilizing news with marginal effect</div>
        </div>
      </div>
    </div>
  </div>

  <div class="gsec">
    <div class="gsec-n">Section 03</div>
    <div class="gsec-t">Example Report \u2014 \u201CTaiwan semiconductor supply chain Q2 2026\u201D</div>
    <div class="ra-findings">
      <div class="ra-finding">
        <div class="ra-chip h">HIGH</div>
        <div>
          <div class="ra-hl">TSMC 3nm fab maintenance pushes Q3 deliveries</div>
          <div class="ra-impact">Lead times for advanced-node orders extending 2\u20134 weeks; downstream logic ICs affected first.</div>
          <div class="ra-source">[source] reuters.com/tech/\u2026</div>
        </div>
      </div>
      <div class="ra-finding">
        <div class="ra-chip m">MED</div>
        <div>
          <div class="ra-hl">US proposes 25% tariff on China-origin wafers</div>
          <div class="ra-impact">Impacts ~15% of non-Taiwan Asian suppliers; comment window closes mid-Q2.</div>
          <div class="ra-source">[source] bloomberg.com/news/\u2026</div>
        </div>
      </div>
      <div class="ra-finding">
        <div class="ra-chip m">MED</div>
        <div>
          <div class="ra-hl">Taiwan Strait joint military exercises scheduled</div>
          <div class="ra-impact">Commercial shipping insurers signal 5\u201310% premium uptick for Q2 sailings.</div>
          <div class="ra-source">[source] ft.com/content/\u2026</div>
        </div>
      </div>
      <div class="ra-finding">
        <div class="ra-chip l">LOW</div>
        <div>
          <div class="ra-hl">South Korea expands semi export guarantees</div>
          <div class="ra-impact">Marginal stabilization signal for memory supply; limited effect on logic sourcing.</div>
          <div class="ra-source">[source] koreaherald.com/\u2026</div>
        </div>
      </div>
    </div>
    <div class="ra-overall"><strong>Overall risk assessment:</strong> Moderate-to-high risk on Taiwan-sourced advanced-node components. Monitor US tariff rulemaking weekly; hedge with Korea / Japan capacity where feasible.</div>
  </div>
</div>
<div id="panel-lp">
  <div class="pclose" onclick="closeLpPanel()">\u2715</div>
  <div class="ph">LP Optimizer \u2014 Cost \u00d7 Risk Allocation</div>
  <div class="psub">PuLP / CBC solver \u00b7 MIP when country-diversified \u00b7 user-approved before execution \u00b7 supports what-if re-runs</div>

  <div class="gsec">
    <div class="gsec-n">Section 01</div>
    <div class="gsec-t">Dispatch Flow \u2014 Solve \u00b7 Review \u00b7 Approve or Modify</div>
    <svg class="fan-svg" viewBox="0 0 900 430" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <marker id="arrGl" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L7,4 L0,8 Z" fill="#76b900"/>
        </marker>
        <marker id="arrGlF" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L7,4 L0,8 Z" fill="#76b900" fill-opacity="0.5"/>
        </marker>
        <marker id="arrOl" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L7,4 L0,8 Z" fill="#e0a020"/>
        </marker>
      </defs>

      <!-- Upstream -->
      <text x="20" y="22" fill="#666" font-family="Inter,sans-serif" font-size="10" font-weight="700" letter-spacing="0.15em">UPSTREAM \u00b7 SHARED BY ALL AGENTS</text>
      <line x1="300" y1="18" x2="880" y2="18" stroke="rgba(118,185,0,0.2)" stroke-width="1"/>
      <g opacity="0.8">
        <rect x="30" y="40" width="140" height="46" rx="3" fill="rgba(255,255,255,0.04)" stroke="#555"/>
        <text x="100" y="68" text-anchor="middle" fill="#bbb" font-family="Inter,sans-serif" font-size="13" font-style="italic">user query</text>
        <line x1="170" y1="63" x2="204" y2="63" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGlF)" opacity="0.7"/>
        <rect x="210" y="40" width="190" height="46" rx="3" fill="rgba(118,185,0,0.04)" stroke="rgba(118,185,0,0.55)"/>
        <text x="305" y="62" text-anchor="middle" fill="#ddd" font-family="Inter,sans-serif" font-size="13" font-weight="600">Orchestrator</text>
        <text x="305" y="78" text-anchor="middle" fill="#888" font-family="SF Mono,monospace" font-size="10">picks run_optimization + params</text>
        <line x1="400" y1="63" x2="434" y2="63" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGlF)" opacity="0.7"/>
        <rect x="440" y="40" width="140" height="46" rx="3" fill="rgba(118,185,0,0.08)" stroke="rgba(118,185,0,0.75)"/>
        <text x="510" y="62" text-anchor="middle" fill="#ddd" font-family="Inter,sans-serif" font-size="13" font-weight="600">Plan</text>
        <text x="510" y="78" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="10">user-approved \u2713</text>
      </g>

      <!-- connector -->
      <path d="M 510 86 C 510 130, 130 120, 130 166" stroke="#76b900" stroke-width="1.5" fill="none" marker-end="url(#arrGl)"/>

      <!-- Row 2 label -->
      <text x="20" y="154" fill="#76b900" font-family="Inter,sans-serif" font-size="10.5" font-weight="700" letter-spacing="0.15em">LP OPTIMIZER \u00b7 PHASE 2</text>
      <line x1="195" y1="150" x2="880" y2="150" stroke="rgba(118,185,0,0.35)" stroke-width="1"/>

      <!-- params -->
      <rect x="30" y="170" width="200" height="80" rx="4" fill="rgba(118,185,0,0.04)" stroke="rgba(118,185,0,0.55)"/>
      <text x="130" y="192" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="10.5" font-weight="700" letter-spacing="0.12em">LP PARAMS</text>
      <text x="130" y="212" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="10.5">product, \u03bb_risk, budget</text>
      <text x="130" y="228" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="10.5">diversification, exclusions</text>
      <text x="130" y="244" text-anchor="middle" fill="#888" font-family="SF Mono,monospace" font-size="10">urgency, service_level</text>

      <line x1="230" y1="210" x2="264" y2="210" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGl)"/>

      <!-- run_optimization -->
      <rect x="270" y="166" width="220" height="90" rx="4" fill="rgba(118,185,0,0.15)" stroke="#76b900" stroke-width="2.5"/>
      <text x="380" y="192" text-anchor="middle" fill="#fff" font-family="Inter,sans-serif" font-size="16" font-weight="700">\u2699 run_optimization</text>
      <text x="380" y="214" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="11.5">build LpProblem \u00b7 add constraints</text>
      <text x="380" y="232" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="11.5">PuLP / CBC solver \u00b7 &lt; 1s</text>
      <text x="380" y="248" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="10">MIP when diversification = country</text>

      <line x1="490" y1="210" x2="524" y2="210" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGl)"/>

      <!-- Result -->
      <rect x="530" y="170" width="170" height="80" rx="4" fill="rgba(118,185,0,0.12)" stroke="#76b900" stroke-width="1.8"/>
      <text x="615" y="196" text-anchor="middle" fill="#fff" font-family="Inter,sans-serif" font-size="14" font-weight="700">LP Result</text>
      <text x="615" y="218" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="10.5">allocation + cost</text>
      <text x="615" y="236" text-anchor="middle" fill="#888" font-family="SF Mono,monospace" font-size="10">+ diagnostics</text>

      <line x1="700" y1="210" x2="734" y2="210" stroke="#e0a020" stroke-width="1.5" marker-end="url(#arrOl)"/>

      <!-- interrupt() -->
      <rect x="740" y="170" width="150" height="80" rx="4" fill="rgba(224,160,32,0.08)" stroke="#e0a020" stroke-width="2"/>
      <text x="815" y="196" text-anchor="middle" fill="#e0a020" font-family="Inter,sans-serif" font-size="15" font-weight="700">\u23F8 interrupt()</text>
      <text x="815" y="218" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="10.5">LP approval gate</text>
      <text x="815" y="236" text-anchor="middle" fill="#888" font-family="SF Mono,monospace" font-size="10">lp_agent.py:202</text>

      <!-- Branches from interrupt -->
      <!-- Approve branch (down-right to Done) -->
      <path d="M 815 250 L 815 295" stroke="#76b900" stroke-width="1.5" fill="none" marker-end="url(#arrGl)"/>
      <text x="830" y="278" fill="#76b900" font-family="Inter,sans-serif" font-size="11" font-weight="600">\u2713 approve</text>

      <rect x="740" y="298" width="150" height="46" rx="3" fill="rgba(118,185,0,0.15)" stroke="#76b900" stroke-width="1.8"/>
      <text x="815" y="325" text-anchor="middle" fill="#fff" font-family="Inter,sans-serif" font-size="13" font-weight="700">Accept allocation</text>

      <!-- Modify branch (loop back to params) -->
      <path d="M 740 210 C 680 340, 260 340, 130 260" stroke="#e0a020" stroke-width="1.5" fill="none" marker-end="url(#arrOl)" stroke-dasharray="5 4"/>
      <text x="420" y="360" fill="#e0a020" font-family="Inter,sans-serif" font-size="12" font-weight="700">\u21B2 modify: +exclusions / +urgency / new \u03bb_risk \u2014 merge_with_prior() \u2192 re-solve</text>

      <!-- Synth skip -->
      <g opacity="0.5">
        <rect x="30" y="384" width="170" height="40" rx="4" fill="rgba(128,128,128,0.08)" stroke="rgba(128,128,128,0.6)" stroke-width="1.2" stroke-dasharray="4 3"/>
        <text x="115" y="400" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="12" font-weight="600">Synthesizer</text>
        <text x="115" y="416" text-anchor="middle" fill="#c04040" font-family="Inter,sans-serif" font-size="10" font-weight="700" letter-spacing="0.12em">SKIPPED</text>
        <line x1="33" y1="406" x2="197" y2="406" stroke="#c04040" stroke-width="1" opacity="0.7"/>
      </g>
      <text x="220" y="408" fill="#888" font-family="Inter,sans-serif" font-size="11.5" font-style="italic">\u2190 LP output is already structured (allocation table + cost summary), no LLM summary needed</text>
    </svg>
  </div>

  <div class="gsec">
    <div class="gsec-n">Section 02</div>
    <div class="gsec-t">Objective Function \u2014 The Cost \u00d7 Risk Tradeoff</div>
    <div class="lp-formula">
      <div class="lp-obj">
        <span style="font-size:20px;color:#888;">min</span>
        &nbsp;\u03a3<sub>j</sub>&nbsp;
        <span class="lp-t-cost">cost<sub>j</sub></span>
        &nbsp;\u00d7&nbsp;
        ( 1 + <span class="lp-t-risk">\u03bb<sub>risk</sub></span> \u00d7 <span class="lp-t-risk">risk<sub>j</sub></span>
        + <span class="lp-t-urg">\u03bb<sub>urg</sub></span> \u00d7 <span class="lp-t-urg">lt_norm<sub>j</sub></span> )
        &nbsp;\u00d7&nbsp;
        <span class="lp-t-x">x<sub>j</sub></span>
      </div>
    </div>
    <div class="lp-legend">
      <div class="lp-leg-row"><span class="lp-leg-k lp-t-cost">cost<sub>j</sub></span><span class="lp-leg-v">Landed unit cost (USD) \u2014 base price + tariff + logistics</span></div>
      <div class="lp-leg-row"><span class="lp-leg-k lp-t-x">x<sub>j</sub></span><span class="lp-leg-v">Decision variable: units allocated to supplier j (continuous, \u2265 0)</span></div>
      <div class="lp-leg-row"><span class="lp-leg-k lp-t-risk">\u03bb<sub>risk</sub></span><span class="lp-leg-v">User-set risk aversion [0,1] \u2014 0 = pure cost, 1 = pure risk</span></div>
      <div class="lp-leg-row"><span class="lp-leg-k lp-t-risk">risk<sub>j</sub></span><span class="lp-leg-v">Normalized risk penalty [0,1] from scoring layer</span></div>
      <div class="lp-leg-row"><span class="lp-leg-k lp-t-urg">\u03bb<sub>urg</sub></span><span class="lp-leg-v">Urgency weight \u2014 0.25 if urgent, 0 otherwise</span></div>
      <div class="lp-leg-row"><span class="lp-leg-k lp-t-urg">lt_norm<sub>j</sub></span><span class="lp-leg-v">Normalized lead time [0,1] \u2014 0 = fastest supplier, 1 = slowest</span></div>
    </div>
  </div>

  <div class="gsec">
    <div class="gsec-n">Section 03</div>
    <div class="gsec-t">Active Constraints \u2014 Three Types</div>
    <div class="lp-constr">
      <div class="lp-c-col">
        <div class="lp-c-h">Linear <span class="lp-c-tag lin">LIN</span></div>
        <div class="lp-c-item">
          <div class="lp-c-name">C1 \u00b7 demand fulfillment</div>
          <div class="lp-c-desc">\u03a3 x<sub>j</sub> \u2265 D \u00b7 service_level (default sl=1.0)</div>
        </div>
        <div class="lp-c-item">
          <div class="lp-c-name">C2 \u00b7 budget cap</div>
          <div class="lp-c-desc">\u03a3 cost<sub>j</sub>\u00b7x<sub>j</sub> \u2264 B (optional; skipped if None)</div>
        </div>
        <div class="lp-c-item">
          <div class="lp-c-name">C4 \u00b7 per-supplier share</div>
          <div class="lp-c-desc">x<sub>j</sub> \u2264 \u03b1 \u00b7 D when diversification = "supplier_share_only"</div>
        </div>
      </div>
      <div class="lp-c-col">
        <div class="lp-c-h">Mixed-Integer <span class="lp-c-tag mip">MIP</span></div>
        <div class="lp-c-item">
          <div class="lp-c-name">C3a \u00b7 exactly 3 suppliers</div>
          <div class="lp-c-desc">\u03a3 y<sub>j</sub> = 3 \u00b7 binary y<sub>j</sub> \u2208 {0,1}</div>
        </div>
        <div class="lp-c-item">
          <div class="lp-c-name">C3b \u00b7 max 1 per country</div>
          <div class="lp-c-desc">\u03a3<sub>j \u2208 country c</sub> y<sub>j</sub> \u2264 1 for each country c</div>
        </div>
        <div class="lp-c-item">
          <div class="lp-c-name">C3c \u00b7 30\u201335% share each</div>
          <div class="lp-c-desc">0.30 D \u00b7 y<sub>j</sub> \u2264 x<sub>j</sub> \u2264 0.35 D \u00b7 y<sub>j</sub> (tied to y)</div>
        </div>
      </div>
      <div class="lp-c-col">
        <div class="lp-c-h">Pre-filter <span class="lp-c-tag flt">FLT</span></div>
        <div class="lp-c-item">
          <div class="lp-c-name">compliance threshold</div>
          <div class="lp-c-desc">Suppliers below eligibility=0.60 dropped <em>before</em> LP build</div>
        </div>
        <div class="lp-c-item">
          <div class="lp-c-name">supplier exclusion</div>
          <div class="lp-c-desc">exclude_supplier_ids list removed pre-LP (what-if scenarios)</div>
        </div>
        <div class="lp-c-item">
          <div class="lp-c-name">avoid-tier fallback</div>
          <div class="lp-c-desc">Prefer non-Avoid pool; fall back with warning if infeasible</div>
        </div>
      </div>
    </div>
    <div class="tl-caption">Diagnostics report which constraints are binding \u00b7 MOQ is tracked post-solve (not hard-enforced)</div>
  </div>
</div>
<div id="panel-chart">
  <div class="pclose" onclick="closeChartPanel()">\u2715</div>
  <div class="ph">Chart Builder \u2014 7 Visualization Tools</div>
  <div class="psub">Zero LLM in loop \u00b7 matplotlib PNG output \u00b7 skips synthesizer \u00b7 auto-scores suppliers when needed</div>

  <div class="gsec">
    <div class="gsec-n">Section 01</div>
    <div class="gsec-t">Dispatch Flow \u2014 Phase 2 Visualization Fast Path</div>
    <svg class="fan-svg" viewBox="0 0 900 380" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <marker id="arrGc" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L7,4 L0,8 Z" fill="#76b900"/>
        </marker>
        <marker id="arrGcF" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L7,4 L0,8 Z" fill="#76b900" fill-opacity="0.5"/>
        </marker>
      </defs>

      <!-- Upstream -->
      <text x="20" y="22" fill="#666" font-family="Inter,sans-serif" font-size="10" font-weight="700" letter-spacing="0.15em">UPSTREAM \u00b7 SHARED BY ALL AGENTS</text>
      <line x1="300" y1="18" x2="880" y2="18" stroke="rgba(118,185,0,0.2)" stroke-width="1"/>
      <g opacity="0.8">
        <rect x="30" y="40" width="140" height="46" rx="3" fill="rgba(255,255,255,0.04)" stroke="#555"/>
        <text x="100" y="68" text-anchor="middle" fill="#bbb" font-family="Inter,sans-serif" font-size="13" font-style="italic">user query</text>
        <line x1="170" y1="63" x2="204" y2="63" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGcF)" opacity="0.7"/>
        <rect x="210" y="40" width="190" height="46" rx="3" fill="rgba(118,185,0,0.04)" stroke="rgba(118,185,0,0.55)"/>
        <text x="305" y="62" text-anchor="middle" fill="#ddd" font-family="Inter,sans-serif" font-size="13" font-weight="600">Orchestrator</text>
        <text x="305" y="78" text-anchor="middle" fill="#888" font-family="SF Mono,monospace" font-size="10">picks chart tool + params</text>
        <line x1="400" y1="63" x2="434" y2="63" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGcF)" opacity="0.7"/>
        <rect x="440" y="40" width="140" height="46" rx="3" fill="rgba(118,185,0,0.08)" stroke="rgba(118,185,0,0.75)"/>
        <text x="510" y="62" text-anchor="middle" fill="#ddd" font-family="Inter,sans-serif" font-size="13" font-weight="600">Plan</text>
        <text x="510" y="78" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="10">user-approved \u2713</text>
      </g>

      <path d="M 510 86 C 510 140, 130 130, 130 174" stroke="#76b900" stroke-width="1.5" fill="none" marker-end="url(#arrGc)"/>

      <text x="20" y="162" fill="#76b900" font-family="Inter,sans-serif" font-size="10.5" font-weight="700" letter-spacing="0.15em">CHART BUILDER \u00b7 PHASE 2</text>
      <line x1="195" y1="158" x2="880" y2="158" stroke="rgba(118,185,0,0.35)" stroke-width="1"/>

      <!-- tool+params -->
      <rect x="30" y="178" width="200" height="80" rx="4" fill="rgba(118,185,0,0.04)" stroke="rgba(118,185,0,0.55)"/>
      <text x="130" y="200" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="10.5" font-weight="700" letter-spacing="0.12em">TOOL + PARAMS</text>
      <text x="130" y="222" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="11.5">plot_score_breakdown</text>
      <text x="130" y="242" text-anchor="middle" fill="#888" font-family="SF Mono,monospace" font-size="10.5">{ supplier_ids, Q, \u03bb_risk }</text>

      <line x1="230" y1="218" x2="264" y2="218" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGc)"/>

      <!-- Dispatch -->
      <rect x="270" y="168" width="280" height="100" rx="4" fill="rgba(118,185,0,0.15)" stroke="#76b900" stroke-width="2.5"/>
      <text x="410" y="196" text-anchor="middle" fill="#fff" font-family="Inter,sans-serif" font-size="17" font-weight="700">\u2699 DISPATCH</text>
      <text x="410" y="220" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="12.5">chart_tool(**params)</text>
      <text x="410" y="240" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="12.5">\u2192 matplotlib figure</text>
      <text x="410" y="258" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="10.5">auto-score fallback \u00b7 ~0.1\u20130.5s</text>

      <rect x="290" y="280" width="240" height="26" rx="3" fill="rgba(224,160,32,0.1)" stroke="#e0a020" stroke-width="1"/>
      <text x="410" y="297" text-anchor="middle" fill="#e0a020" font-family="Inter,sans-serif" font-size="11.5" font-weight="700" letter-spacing="0.14em">\u26A1 ZERO LLM IN LOOP</text>

      <line x1="550" y1="218" x2="584" y2="218" stroke="#76b900" stroke-width="1.5" marker-end="url(#arrGc)"/>

      <!-- PNG output -->
      <rect x="590" y="178" width="170" height="80" rx="4" fill="rgba(118,185,0,0.12)" stroke="#76b900" stroke-width="1.8"/>
      <text x="675" y="204" text-anchor="middle" fill="#fff" font-family="Inter,sans-serif" font-size="14" font-weight="700">PNG Output</text>
      <text x="675" y="224" text-anchor="middle" fill="#76b900" font-family="SF Mono,monospace" font-size="10.5">base64-encoded</text>
      <text x="675" y="244" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="10">displayed in chat</text>

      <line x1="760" y1="218" x2="794" y2="218" stroke="rgba(192,64,64,0.6)" stroke-width="1.5" stroke-dasharray="4 3"/>
      <text x="777" y="211" text-anchor="middle" fill="#c04040" font-family="Inter,sans-serif" font-size="14" font-weight="700">\u2717</text>
      <g opacity="0.55">
        <rect x="800" y="188" width="95" height="60" rx="4" fill="rgba(128,128,128,0.08)" stroke="rgba(128,128,128,0.6)" stroke-width="1.2" stroke-dasharray="4 3"/>
        <text x="848" y="214" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="11.5" font-weight="600">Synthesizer</text>
        <text x="848" y="232" text-anchor="middle" fill="#c04040" font-family="Inter,sans-serif" font-size="10" font-weight="700" letter-spacing="0.12em">SKIPPED</text>
        <line x1="803" y1="216" x2="892" y2="216" stroke="#c04040" stroke-width="1.2" opacity="0.7"/>
      </g>

      <text x="450" y="352" text-anchor="middle" fill="#888" font-family="Inter,sans-serif" font-size="12">Images are self-explanatory \u2014 no LLM summary needed; chart appears directly in the chat response</text>
    </svg>
  </div>

  <div class="gsec">
    <div class="gsec-n">Section 02</div>
    <div class="gsec-t">Toolset \u2014 7 Charts Grouped by Focus <span style="color:#888; font-weight:400; font-size:13px; margin-left:12px;">hover any tool for details</span></div>
    <div class="ch-flow">
      <div class="ch-col">
        <div class="ch-h">Supplier Focus <span class="ch-n">2</span></div>
        <ul class="ch-list">
          <li title="Supplier score breakdown chart \u2014 visualizes cost drivers and risk penalty components for each supplier."><span class="ch-icon">\u25B0</span><span class="ch-name">plot_score_breakdown</span></li>
          <li title="Side-by-side supplier comparison: cost, price volatility, bulk discount, lead time."><span class="ch-icon">\u25A4</span><span class="ch-name">plot_supplier_comparison</span></li>
        </ul>
      </div>
      <div class="ch-col">
        <div class="ch-h">Country / Geography <span class="ch-n">1</span></div>
        <ul class="ch-list">
          <li title="Country-level LPI (logistics) and WGI (governance) indicators for sourcing context."><span class="ch-icon">\u25D3</span><span class="ch-name">plot_country_comparison</span></li>
        </ul>
      </div>
      <div class="ch-col">
        <div class="ch-h">Pricing Dynamics <span class="ch-n">2</span></div>
        <ul class="ch-list">
          <li title="Real-price historical trend for a single country + product."><span class="ch-icon">\u2197</span><span class="ch-name">plot_price_trend</span></li>
          <li title="Indexed product price vs. commodity baseline \u2014 shows pass-through of raw material cost."><span class="ch-icon">\u2933</span><span class="ch-name">plot_price_vs_commodity</span></li>
        </ul>
      </div>
      <div class="ch-col">
        <div class="ch-h">Volatility Analysis <span class="ch-n">2</span></div>
        <ul class="ch-list">
          <li title="Rolling price volatility trend for a single country + product (configurable window)."><span class="ch-icon">\u223F</span><span class="ch-name">plot_volatility_trend</span></li>
          <li title="Multi-country rolling volatility comparison \u2014 where is pricing least stable?"><span class="ch-icon">\u2248</span><span class="ch-name">plot_cross_country_volatility</span></li>
        </ul>
      </div>
    </div>
  </div>
</div>
<script>
function closePanel() { document.getElementById("panel").style.display = "none"; }
function closeOrchPanel() { document.getElementById("panel-orch").style.display = "none"; }
function closeDataPanel() { document.getElementById("panel-data").style.display = "none"; }
function closeRiskPanel() { document.getElementById("panel-risk").style.display = "none"; }
function closeLpPanel() { document.getElementById("panel-lp").style.display = "none"; }
function closeChartPanel() { document.getElementById("panel-chart").style.display = "none"; }
var canvas = document.getElementById("c");
var ctx = canvas.getContext("2d");
var tip = document.getElementById("tip");
var DPR = window.devicePixelRatio || 1;
var TAU = Math.PI * 2;
var W, H;

function resize() {
  W = canvas.parentElement.clientWidth || 1000;
  H = 1150;
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
var NW = 210, NH = 66, OW = 175, OH = 54;
var RG = 120, CG = 45;
var cx = W / 2;

// Row Y positions (more spacing)
var RY = {
  user: 60,
  orch: 60 + RG,
  phase1: 60 + RG * 2,
  router: 60 + RG * 3,
  phase2: 60 + RG * 4,
  synth: 60 + RG * 5.5,
  end: 60 + RG * 6.5,
  resp: 60 + RG * 7.5,
};

// Step number badges for each node
var STEP_BADGES = {
  user:null, orch_classify:"1a", orch_fewshot:"1b", orch_extract:"1c",
  pipeline_agent:"2", data_agent:"2", risk_agent:"2", router:"3",
  chart_agent:"4", lp_agent:"4", synthesizer:"5", end_node:null, response:"6"
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
  {id:"router", label:"Phase Router", cx:cx, cy:RY.router, w:NW, h:54, key:"router"},
  // Row 4: Phase 2 (parallel fan-out)
  {id:"chart_agent", label:"Chart Builder", cx:cx-(NW/2+CG/2), cy:RY.phase2, w:NW, h:NH, key:"chart_agent"},
  {id:"lp_agent", label:"LP Optimizer", cx:cx+(NW/2+CG/2), cy:RY.phase2, w:NW, h:NH, key:"lp_agent"},
  // Row 5: Synthesizer (conditional)
  {id:"synthesizer", label:"Synthesizer", cx:cx, cy:RY.synth, w:NW, h:NH, key:"synthesizer"},
  // Row 6: END
  {id:"end_node", label:"END", cx:cx+(NW+CG), cy:RY.end, w:120, h:50, key:null},
  // Row 7: Response
  {id:"response", label:"Response", cx:cx, cy:RY.resp, w:NW, h:NH, key:null},
];
nodes.forEach(function(n) { n.x = n.cx - n.w/2; n.y = n.cy - n.h/2; });

// Compute orchestrator group bounding box (used for hit-testing + rendering)
var orchBox = null;
(function() {
  var _ons = nodes.filter(function(n) { return n.key === "orchestrator"; });
  if (!_ons.length) return;
  var _pad = 20, _topPad = 32;
  var _x = Math.min.apply(null, _ons.map(function(n){return n.x})) - _pad;
  var _y = Math.min.apply(null, _ons.map(function(n){return n.y})) - _topPad;
  var _w = Math.max.apply(null, _ons.map(function(n){return n.x+n.w})) - _x + _pad;
  var _h = Math.max.apply(null, _ons.map(function(n){return n.y+n.h})) - _y + _pad;
  orchBox = {x:_x, y:_y, w:_w, h:_h};
})();

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

// Critical path: User → Orchestrator → Pipeline → Router → LP → END → Response
var CRITICAL_PATH_EDGES = {
  "user|orch_classify":true,
  "orch_classify|orch_fewshot":true,
  "orch_fewshot|orch_extract":true,
  "orch_extract|pipeline_agent":true,
  "pipeline_agent|router":true,
  "router|lp_agent":true,
  "lp_agent|end_node":true,
  "end_node|response":true
};

// For orchestrator internal edges, connect right side → left side (horizontal)
var edges = EDGES.map(function(e) {
  var a = nodeMap[e[0]], b = nodeMap[e[1]];
  if (!a || !b) return null;
  var isHoriz = (a.cy === b.cy); // same row = horizontal
  var isCritical = CRITICAL_PATH_EDGES[e[0]+"|"+e[1]] || false;
  if (isHoriz) {
    return {x1:a.cx+a.w/2, y1:a.cy, x2:b.cx-b.w/2, y2:b.cy, fromRow:rowOf[e[0]]||0, horiz:true, critical:isCritical};
  }
  return {x1:a.cx, y1:a.cy+a.h/2, x2:b.cx, y2:b.cy-b.h/2, fromRow:rowOf[e[0]]||0, horiz:false, critical:isCritical};
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
var EXPANDABLE = {
  pipeline_agent: {panel:"panel", tip:"Click to expand all 10 tools"},
  data_agent:     {panel:"panel-data", tip:"Click to see ReAct loop + schema"},
  risk_agent:     {panel:"panel-risk", tip:"Click to see news pipeline + risk levels"},
  lp_agent:       {panel:"panel-lp", tip:"Click to see objective + constraints + approval loop"},
  chart_agent:    {panel:"panel-chart", tip:"Click to see 7 chart tools grouped by focus"}
};
function inOrchBox(mx, my) {
  return orchBox && mx >= orchBox.x && mx <= orchBox.x+orchBox.w
                 && my >= orchBox.y && my <= orchBox.y+orchBox.h;
}
canvas.addEventListener("mousemove", function(evt) {
  var rect = canvas.getBoundingClientRect();
  var mx = evt.clientX - rect.left, my = evt.clientY - rect.top;
  hoverNode = null;
  for (var i = 0; i < nodes.length; i++) {
    var n = nodes[i];
    if (mx >= n.x && mx <= n.x+n.w && my >= n.y && my <= n.y+n.h) { hoverNode = n; break; }
  }
  var isOrchHover = (hoverNode && hoverNode.key === "orchestrator") || (!hoverNode && inOrchBox(mx, my));
  canvas.style.cursor = ((hoverNode && EXPANDABLE[hoverNode.id]) || isOrchHover) ? "pointer" : "default";
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
    if (EXPANDABLE[hoverNode.id]) html += '<div class="td" style="color:#76b900;font-weight:600;">\u25B6 ' + EXPANDABLE[hoverNode.id].tip + '</div>';
    if (key === "orchestrator") html += '<div class="td" style="color:#76b900;font-weight:600;">\u25B6 Click anywhere in the dashed box to expand</div>';
    tip.innerHTML = html;
    tip.style.display = "block";
    var tx = mx + 14, ty = my - 10;
    if (tx + 320 > W) tx = mx - 330;
    if (ty + 180 > H) ty = my - 180;
    tip.style.left = tx + "px";
    tip.style.top = ty + "px";
  } else if (isOrchHover) {
    var html = '<div class="tl">Orchestrator</div>'
      + '<div class="td">Hybrid LLM orchestrator. Classifies user intent, extracts parameters deterministically, generates execution plan.</div>'
      + '<div class="td" style="color:#76b900;font-weight:600;">\u25B6 Click to see 4-stage internals</div>';
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
canvas.addEventListener("click", function(evt) {
  var rect = canvas.getBoundingClientRect();
  var mx = evt.clientX - rect.left, my = evt.clientY - rect.top;
  var clickedNode = null;
  for (var i = 0; i < nodes.length; i++) {
    var n = nodes[i];
    if (mx >= n.x && mx <= n.x+n.w && my >= n.y && my <= n.y+n.h) { clickedNode = n; break; }
  }
  if (clickedNode && EXPANDABLE[clickedNode.id]) {
    document.getElementById(EXPANDABLE[clickedNode.id].panel).style.display = "block";
    tip.style.display = "none";
    return;
  }
  if ((clickedNode && clickedNode.key === "orchestrator") || (!clickedNode && inOrchBox(mx, my))) {
    document.getElementById("panel-orch").style.display = "block";
    tip.style.display = "none";
  }
});
document.addEventListener("keydown", function(e) {
  if (e.key === "Escape") { closePanel(); closeOrchPanel(); closeDataPanel(); closeRiskPanel(); closeLpPanel(); closeChartPanel(); }
});

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
    var pad = 20;
    var gx = Math.min.apply(null, orchNs.map(function(n){return n.x})) - pad;
    var gy = Math.min.apply(null, orchNs.map(function(n){return n.y})) - 32;
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
    ctx.font = "700 13px Inter,sans-serif"; ctx.fillStyle = "#76b900";
    ctx.textAlign = "left";
    ctx.fillText("ORCHESTRATOR", gx+12, gy+18);
    ctx.restore();

    // Expand "+" badge on orchestrator group box (top-right, pulsing)
    if (progress > 0.3) {
      var opulse = 0.6 + 0.4 * Math.sin(elapsed/400);
      var obx = gx + gw - 18;
      var oby = gy + 18;
      var obr = 12;
      ctx.save();
      ctx.beginPath();
      ctx.arc(obx, oby, obr, 0, TAU);
      ctx.fillStyle = "rgba(118,185,0," + (0.85*opulse) + ")";
      ctx.fill();
      ctx.strokeStyle = "#76b900"; ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.font = "700 15px Inter,sans-serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillStyle = "#0A1F17";
      ctx.fillText("+", obx, oby);
      ctx.restore();
    }
  }

  // Phase labels with business value descriptions
  var phases = [
    {y:RY.phase1, label:"PHASE 1 \u2014 PARALLEL DATA RETRIEVAL", biz:"Retrieve demand forecasts, inventory positions, and risk signals"},
    {y:RY.phase2, label:"PHASE 2 \u2014 ANALYSIS & OPTIMIZATION", biz:"Generate supplier scores, charts, and optimized procurement plans"}
  ];
  phases.forEach(function(pl) {
    var a = easeOut(clamp((progress-0.15)*3,0,1));
    ctx.save(); ctx.globalAlpha = a*0.4;
    ctx.font = "700 12px Inter,sans-serif"; ctx.fillStyle = "#76b900";
    ctx.textAlign = "center";
    ctx.fillText(pl.label, cx, pl.y - NH/2 - 20);
    ctx.restore();
    // Business value description below the phase label
    ctx.save(); ctx.globalAlpha = a*0.3;
    ctx.font = "400 11px Inter,sans-serif"; ctx.fillStyle = "#888";
    ctx.textAlign = "center";
    ctx.fillText(pl.biz, cx, pl.y - NH/2 - 6);
    ctx.restore();
  });

  // Synthesizer business description
  var synthA = easeOut(clamp((progress-0.15)*3,0,1));
  ctx.save(); ctx.globalAlpha = synthA*0.3;
  ctx.font = "400 11px Inter,sans-serif"; ctx.fillStyle = "#888";
  ctx.textAlign = "center";
  ctx.fillText("Consolidate findings into executive-ready insights", cx, RY.synth - NH/2 - 10);
  ctx.restore();

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
    ctx.strokeStyle = e.critical ? "rgba(118,185,0,0.45)" : "rgba(118,185,0,0.3)";
    ctx.lineWidth = e.critical ? 2.5 : 1.5;
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

    ctx.font = "700 " + (n.h < 58 ? "13" : "16") + "px Inter,sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillStyle = isTerminal ? "#999" : "#fff";
    ctx.fillText(n.label.toUpperCase(), n.cx, n.cy);

    // Step number badge (top-left corner)
    var badge = STEP_BADGES[n.id];
    if (badge) {
      var bx = n.x + 10;
      var by = n.y + 10;
      var br = 12;
      ctx.beginPath();
      ctx.arc(bx, by, br, 0, TAU);
      ctx.fillStyle = "#76b900";
      ctx.fill();
      ctx.font = "700 11px Inter,sans-serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillStyle = "#000";
      ctx.fillText(badge, bx, by);
    }

    // Expand indicator (bottom-right corner, pulsing) for expandable nodes
    if (EXPANDABLE[n.id]) {
      var epulse = 0.6 + 0.4 * Math.sin(elapsed/400);
      var ebx = n.x + n.w - 14;
      var eby = n.y + n.h - 14;
      var ebr = 11;
      ctx.beginPath();
      ctx.arc(ebx, eby, ebr, 0, TAU);
      ctx.fillStyle = "rgba(118,185,0," + (0.85*epulse) + ")";
      ctx.fill();
      ctx.strokeStyle = "#76b900"; ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.font = "700 14px Inter,sans-serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillStyle = "#0A1F17";
      ctx.fillText("+", ebx, eby);
    }

    ctx.restore();
  });

  // Legend (bottom-left, above footer)
  if (progress > 0.7) {
    var legA = clamp((progress-0.7)/0.2, 0, 1);
    ctx.save(); ctx.globalAlpha = legA;
    var legX = 24;
    var legY = H - 108;
    var legSpacing = 24;
    ctx.font = "400 11px Inter,sans-serif";
    ctx.textBaseline = "middle";

    // Active agent node (green solid border)
    drawRR(legX, legY - 6, 18, 12, 2);
    ctx.strokeStyle = "#76b900"; ctx.lineWidth = 2; ctx.setLineDash([]);
    ctx.stroke();
    ctx.fillStyle = "#888"; ctx.textAlign = "left";
    ctx.fillText("Active agent node", legX + 26, legY);

    // Terminal node (gray border)
    drawRR(legX, legY + legSpacing - 6, 18, 12, 2);
    ctx.strokeStyle = "#555"; ctx.lineWidth = 1; ctx.setLineDash([]);
    ctx.stroke();
    ctx.fillStyle = "#888";
    ctx.fillText("Terminal node (User / Response)", legX + 26, legY + legSpacing);

    // Dashed green box (orchestrator group)
    drawRR(legX, legY + legSpacing*2 - 6, 18, 12, 2);
    ctx.strokeStyle = "#76b900"; ctx.lineWidth = 1; ctx.setLineDash([5,3]);
    ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = "#888";
    ctx.fillText("Orchestrator group", legX + 26, legY + legSpacing*2);

    // Green line with dots (data flow)
    ctx.beginPath();
    ctx.moveTo(legX, legY + legSpacing*3);
    ctx.lineTo(legX + 18, legY + legSpacing*3);
    ctx.strokeStyle = "#76b900"; ctx.lineWidth = 1.5; ctx.setLineDash([]);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(legX + 9, legY + legSpacing*3, 3, 0, TAU);
    ctx.fillStyle = "#76b900"; ctx.fill();
    ctx.fillStyle = "#888";
    ctx.fillText("Data flow", legX + 26, legY + legSpacing*3);

    ctx.restore();
  }

  // Footer labels
  if (progress > 0.8) {
    var ba = clamp((progress-0.8)/0.2, 0, 1);
    ctx.save(); ctx.globalAlpha = ba;
    ctx.font = "600 11px Inter,sans-serif";
    ctx.textAlign = "center"; ctx.fillStyle = "#555";
    ctx.fillText("HOVER NODES FOR DETAILS", cx, H - 14);
    ctx.restore();
  }

  requestAnimationFrame(draw);
}
requestAnimationFrame(draw);
</script></body></html>'''

    components.html(arch_html, height=1160)


# ── Data Pipeline view ───────────────────────────────────────────────────────

def render_data_pipeline():
    """Render interactive animated data pipeline flowchart — public sources to LP."""
    import streamlit.components.v1 as components

    st.markdown(
        "<div style='padding:0.75rem 0 0.25rem;'>"
        "<h2 style='font-family:Inter,sans-serif; font-size:1.3rem; font-weight:700;"
        "color:#ffffff; margin:0 0 0.25rem; letter-spacing:0.02em;'>Data Pipeline</h2>"
        "<p style='font-family:Inter,sans-serif; font-size:0.82rem; color:#888888; margin:0;'>"
        "End-to-end flow from public data sources to LP-ready inputs.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    dp_html = '''<!DOCTYPE html>
<html><head><style>
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#0A1F17; overflow:hidden; font-family:Inter,system-ui,sans-serif; }
canvas { display:block; cursor:crosshair; }
#tip {
  position:absolute; display:none; pointer-events:none;
  background:rgba(10,31,23,0.95); border:1px solid #76b900; border-radius:3px;
  padding:12px 16px; font-size:12px; color:#ccc; max-width:340px;
  box-shadow:0 4px 20px rgba(0,0,0,0.5); z-index:10;
}
#tip .tl { color:#fff; font-weight:700; font-size:14px; text-transform:uppercase;
  letter-spacing:0.06em; margin-bottom:6px; }
#tip .td { color:#aaa; font-size:11.5px; margin-bottom:5px; line-height:1.55; }
#tip .tt { color:#76b900; font-size:11px; margin-top:3px; }
.dpanel { position:absolute; display:none; top:3%; left:4%; width:92%; height:94%;
  background:rgba(10,31,23,0.97); border:1.5px solid #76b900; border-radius:6px;
  padding:28px 32px 24px; box-shadow:0 12px 48px rgba(0,0,0,0.7); z-index:20;
  overflow-y:auto; }
.dpanel .pclose { position:absolute; top:14px; right:18px; font-size:22px; color:#76b900;
  cursor:pointer; font-weight:400; line-height:1; padding:4px 10px;
  border:1px solid transparent; border-radius:3px; transition:border-color 0.15s; }
.dpanel .pclose:hover { border-color:#76b900; }
.dpanel .ph { color:#fff; font-size:22px; font-weight:700; letter-spacing:0.06em;
  text-transform:uppercase; margin-bottom:6px; }
.dpanel .psub { color:#888; font-size:14px; margin-bottom:26px; line-height:1.55; }
.dpanel .gsec { margin-bottom:32px; }
.dpanel .gsec-n { color:#76b900; font-size:11px; font-weight:700; letter-spacing:0.14em;
  text-transform:uppercase; margin-bottom:4px; }
.dpanel .gsec-t { color:#fff; font-size:18px; font-weight:700; margin-bottom:16px;
  letter-spacing:0.02em; }
.dpanel .gcap { color:#888; font-size:12.5px; margin-top:10px; font-style:italic;
  line-height:1.6; }
/* ── DS panel: Public Data Sources ── */
.ds-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin-top:14px; }
.ds-tile { background:rgba(118,185,0,0.04); border:1px solid rgba(118,185,0,0.35);
  border-radius:6px; padding:20px; display:flex; flex-direction:column; gap:10px;
  position:relative; min-height:200px; }
.ds-tile-head { display:flex; align-items:flex-start; justify-content:space-between; gap:6px; }
.ds-icon { font-size:48px; line-height:1; flex-shrink:0; }
.ds-badge { font-size:11px; font-weight:700; letter-spacing:0.08em;
  padding:4px 11px; border-radius:20px; text-transform:uppercase;
  white-space:nowrap; margin-top:4px; flex-shrink:0; }
.ds-badge-log { background:rgba(118,185,0,0.18); color:#76b900; border:1px solid rgba(118,185,0,0.45); }
.ds-badge-gov { background:rgba(0,185,185,0.14); color:#00c4c4; border:1px solid rgba(0,185,185,0.40); }
.ds-badge-cost { background:rgba(224,160,32,0.16); color:#e0a020; border:1px solid rgba(224,160,32,0.42); }
.ds-badge-trd { background:rgba(192,80,80,0.15); color:#e06060; border:1px solid rgba(192,80,80,0.40); }
.ds-name { font-size:15px; font-weight:700; color:#fff; line-height:1.3; margin-top:-2px; }
.ds-cov { display:flex; flex-direction:column; gap:6px; }
.ds-dots { display:flex; flex-wrap:wrap; gap:4px; }
.ds-dot { width:9px; height:9px; border-radius:50%;
  background:rgba(118,185,0,0.22); border:1px solid rgba(118,185,0,0.35); }
.ds-dot.on { background:#76b900; border-color:#76b900; box-shadow:0 0 3px rgba(118,185,0,0.55); }
.ds-cov-label { font-size:11.5px; color:#888; font-family:'SF Mono',Menlo,Consolas,monospace; }
.ds-bar-track { width:100%; height:8px; background:rgba(255,255,255,0.07); border-radius:3px; overflow:hidden; }
.ds-bar-fill { height:100%; border-radius:3px;
  background:linear-gradient(90deg,rgba(118,185,0,0.45) 0%,#76b900 100%); }
.ds-bar-labels { display:flex; justify-content:space-between; }
.ds-bar-labels span { font-size:11.5px; color:#888; font-family:'SF Mono',Menlo,Consolas,monospace; }
.ds-chips { display:flex; flex-wrap:wrap; gap:6px; margin-top:auto; }
.ds-chip { font-size:11px; font-family:'SF Mono',Menlo,Consolas,monospace;
  color:#bbb; background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.10);
  border-radius:20px; padding:3px 10px; white-space:nowrap; }

/* ── CL panel: Cleaning & Normalization ── */
.cl-grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:6px; }
.cl-card { background:rgba(118,185,0,0.04); border:1px solid rgba(118,185,0,0.35);
  border-radius:10px; padding:18px 18px 14px; display:flex; flex-direction:column; gap:10px; }
.cl-card-icon { font-size:30px; line-height:1; }
.cl-card-name { font-size:14.5px; font-weight:700; color:#fff;
  letter-spacing:0.03em; text-transform:uppercase; }
.cl-xform { display:flex; align-items:flex-start; gap:8px; flex-wrap:nowrap; }
.cl-before, .cl-after { font-family:'SF Mono',Menlo,Consolas,monospace;
  font-size:12px; line-height:1.55; border-radius:5px; padding:8px 10px;
  flex:1; min-width:0; word-break:break-all; white-space:pre-wrap; }
.cl-before { color:#c09090; background:rgba(192,144,144,0.08); border:1px solid rgba(192,144,144,0.18); }
.cl-after { color:#76b900; background:rgba(118,185,0,0.07); border:1px solid rgba(118,185,0,0.22); }
.cl-arrow { color:#76b900; font-size:18px; font-weight:700; margin-top:8px;
  flex-shrink:0; line-height:1; }
.cl-note { font-size:12.5px; color:#888; line-height:1.5;
  border-top:1px solid rgba(255,255,255,0.06); padding-top:8px; }
.cl-chips { display:flex; flex-wrap:wrap; gap:9px; margin-top:6px; }
.cl-chip { background:rgba(118,185,0,0.10); border:1px solid rgba(118,185,0,0.40);
  color:#76b900; font-size:13px; font-weight:600; letter-spacing:0.04em;
  border-radius:20px; padding:5px 13px; }
.cl-caption { margin-top:12px; font-size:13px; color:#888; line-height:1.55; }
.cl-caption code { font-family:'SF Mono',Menlo,Consolas,monospace; font-size:11.5px;
  color:#bbb; background:rgba(255,255,255,0.06); border-radius:4px; padding:2px 7px; }

/* ── SN panel: Synthetic Generation ── */
.sn-pipeline-wrap { display:flex; align-items:center; gap:0;
  overflow-x:auto; padding:14px 0 18px;
  scrollbar-width:thin; scrollbar-color:#76b900 #0A1F17; }
.sn-edge-card { flex:0 0 auto; width:110px; padding:14px 10px; border-radius:8px;
  text-align:center; display:flex; flex-direction:column; align-items:center; gap:7px; }
.sn-edge-card.sn-input { border:1.5px dashed #555; background:rgba(255,255,255,0.03); }
.sn-edge-card.sn-output { border:1.5px solid #76b900; background:rgba(118,185,0,0.10); }
.sn-edge-icon { font-size:28px; line-height:1; }
.sn-edge-label { font-size:12px; font-weight:600; line-height:1.3;
  text-transform:uppercase; letter-spacing:0.05em; }
.sn-input .sn-edge-label { color:#888; }
.sn-output .sn-edge-label { color:#76b900; }
.sn-edge-detail { font-size:11px; color:#666; line-height:1.4; text-align:center; }
.sn-output .sn-edge-detail { color:#9dcf40; }
.sn-connector { flex:0 0 auto; display:flex; flex-direction:column;
  align-items:center; justify-content:center; gap:4px; padding:0 6px; min-width:44px; }
.sn-conn-dots { font-size:13px; letter-spacing:1px; color:#76b900; line-height:1; }
.sn-conn-arrow { font-size:22px; color:#76b900; line-height:1; font-weight:700; }
.sn-stage { flex:0 0 auto; width:180px;
  background:linear-gradient(160deg,#0f2a1e 0%,#0d2218 100%);
  border:1px solid #1e4030; border-radius:12px; padding:18px 14px 14px;
  display:flex; flex-direction:column; align-items:center; gap:8px;
  position:relative; transition:border-color 0.2s; }
.sn-stage:hover { border-color:#76b900; }
.sn-badge { width:34px; height:34px; border-radius:50%; background:#76b900;
  color:#0A1F17; font-size:14px; font-weight:800;
  display:flex; align-items:center; justify-content:center; line-height:1; flex-shrink:0; }
.sn-stage-icon { font-size:38px; line-height:1; margin:4px 0; }
.sn-nb-name { font-family:'SF Mono',Menlo,Consolas,monospace; font-size:11px;
  color:#76b900; background:rgba(118,185,0,0.10); border:1px solid rgba(118,185,0,0.25);
  border-radius:4px; padding:4px 8px; letter-spacing:0.02em; text-align:center;
  width:100%; box-sizing:border-box; white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; }
.sn-stat-num { font-size:46px; font-weight:800; color:#fff; line-height:1;
  text-align:center; letter-spacing:-0.02em; }
.sn-stat-num span.sn-tilde { font-size:30px; color:#bbb; vertical-align:middle; font-weight:600; }
.sn-stat-label { font-size:11.5px; color:#76b900; font-weight:600;
  text-align:center; line-height:1.35; letter-spacing:0.03em; }
.sn-entity-chip { font-size:12px; color:#bbb; background:rgba(255,255,255,0.06);
  border-radius:4px; padding:4px 10px; text-align:center; font-weight:500; }
.sn-note { font-size:11.5px; color:#888; text-align:center; line-height:1.5;
  padding-top:4px; border-top:1px solid rgba(255,255,255,0.06); width:100%; }
.sn-why-card { background:linear-gradient(135deg,#0f2a1e 0%,#0d2218 100%);
  border:1px solid #1e4030; border-radius:10px; padding:18px 22px;
  display:flex; gap:18px; align-items:flex-start; margin-top:6px; }
.sn-why-icon { font-size:34px; line-height:1; flex-shrink:0; margin-top:2px; }
.sn-why-body { display:flex; flex-direction:column; gap:6px; }
.sn-why-title { font-size:15px; font-weight:700; color:#fff; letter-spacing:0.02em; }
.sn-why-bullets { list-style:none; padding:0; margin:0;
  display:flex; flex-direction:column; gap:5px; }
.sn-why-bullets li { font-size:13px; color:#bbb; line-height:1.55;
  padding-left:18px; position:relative; }
.sn-why-bullets li::before { content:'\u25B8'; color:#76b900; font-size:11px;
  position:absolute; left:0; top:2px; }

/* ── SW panel: SQL Warehouse ── */
.sw-schema-grid { display:grid; grid-template-columns:1fr 1fr 1fr; gap:14px; margin-top:12px; }
.sw-family-col { display:flex; flex-direction:column; gap:8px; }
.sw-family-header { display:flex; align-items:center; gap:9px; padding:10px 14px;
  border-radius:6px; background:rgba(255,255,255,0.04); margin-bottom:4px; }
.sw-family-icon { font-size:20px; line-height:1; }
.sw-family-name { font-size:14px; font-weight:600; color:#fff;
  text-transform:uppercase; letter-spacing:0.08em; flex:1; }
.sw-family-badge { font-size:12.5px; font-weight:700; padding:3px 10px;
  border-radius:12px; line-height:1.3; }
.sw-badge-dim { background:rgba(56,189,196,0.18); color:#38bdc4; }
.sw-badge-fact { background:rgba(224,160,32,0.18); color:#e0a020; }
.sw-badge-view { background:rgba(118,185,0,0.18); color:#76b900; }
.sw-table-card { padding:10px 12px 10px 14px; border-radius:5px;
  background:rgba(255,255,255,0.03); border-left:4px solid transparent;
  transition:background 0.15s; }
.sw-card-dim { border-left-color:#38bdc4; }
.sw-card-fact { border-left-color:#e0a020; }
.sw-card-view { border-left-color:#76b900; }
.sw-table-name { font-family:'SF Mono',Menlo,Consolas,monospace; font-size:13px;
  color:#76b900; display:block; line-height:1.4; word-break:break-all; }
.sw-table-grain { font-size:11.5px; color:#888; font-style:italic;
  display:block; line-height:1.5; margin-top:3px; }
.sw-ladder { display:flex; flex-direction:column; position:relative;
  padding-left:38px; margin-top:12px; }
.sw-ladder-line { position:absolute; left:14px; top:16px; bottom:40px;
  width:2px; border-left:2px dashed rgba(118,185,0,0.4); }
.sw-ladder-step { display:flex; align-items:flex-start; gap:12px;
  padding:7px 0; position:relative; }
.sw-step-num { position:absolute; left:-38px; top:8px; width:24px; height:24px;
  border-radius:50%; background:#76b900; color:#0A1F17; font-size:12px;
  font-weight:700; display:flex; align-items:center; justify-content:center;
  flex-shrink:0; line-height:1; z-index:1; }
.sw-step-body { display:flex; align-items:center; gap:12px; flex:1; flex-wrap:wrap;
  padding:8px 14px; border-radius:5px; background:rgba(255,255,255,0.03); min-height:38px; }
.sw-step-file { font-family:'SF Mono',Menlo,Consolas,monospace; font-size:13.5px;
  color:#fff; flex:1; }
.sw-step-type { font-size:11px; font-weight:700; text-transform:uppercase;
  letter-spacing:0.1em; padding:3px 10px; border-radius:3px; white-space:nowrap; }
.sw-type-ddl { background:rgba(56,189,196,0.15); color:#38bdc4; }
.sw-type-stage { background:rgba(255,255,255,0.08); color:#bbb; }
.sw-type-data { background:rgba(224,160,32,0.15); color:#e0a020; }
.sw-type-views { background:rgba(118,185,0,0.15); color:#76b900; }
.sw-ladder-warn { margin-top:14px; padding:11px 14px; border-radius:5px;
  background:rgba(224,160,32,0.08); border:1px solid rgba(224,160,32,0.25);
  font-size:12.5px; color:#bbb; line-height:1.55; }
.sw-warn-icon { color:#e0a020; font-style:normal; margin-right:6px; font-size:14px; }
.sw-warn-code { font-family:'SF Mono',Menlo,Consolas,monospace; font-size:12px; color:#e0a020; }
</style></head><body>
<canvas id="c"></canvas>
<div id="tip"></div>

<div id="dp-panel-sources" class="dpanel">
  <div class="pclose" onclick="closeDp('sources')">\u2715</div>
  <div class="ph">Public Data Sources \u2014 9 External Datasets</div>
  <div class="psub">Open government &amp; trade data ingested once \u00b7 powers risk scoring, cost indices, and logistics benchmarks</div>

  <div class="gsec">
    <div class="gsec-n">Visual catalog</div>
    <div class="gsec-t">All datasets \u00b7 grouped by domain</div>
    <div class="ds-grid">

      <div class="ds-tile">
        <div class="ds-tile-head"><div class="ds-icon">\U0001F6A2</div><span class="ds-badge ds-badge-log">LOG</span></div>
        <div class="ds-name">World Bank LPI</div>
        <div class="ds-cov">
          <div class="ds-dots"><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span></div>
          <span class="ds-cov-label">20/20 countries \u00b7 2023 snapshot</span>
        </div>
        <div class="ds-chips"><span class="ds-chip">customs</span><span class="ds-chip">infrastructure</span><span class="ds-chip">logistics</span></div>
      </div>

      <div class="ds-tile">
        <div class="ds-tile-head"><div class="ds-icon">\u2693</div><span class="ds-badge ds-badge-log">LOG</span></div>
        <div class="ds-name">UNCTAD Port Calls</div>
        <div class="ds-cov">
          <div class="ds-dots"><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot"></span><span class="ds-dot"></span><span class="ds-dot"></span><span class="ds-dot"></span><span class="ds-dot"></span><span class="ds-dot"></span><span class="ds-dot"></span><span class="ds-dot"></span><span class="ds-dot"></span><span class="ds-dot"></span><span class="ds-dot"></span></div>
          <span class="ds-cov-label">9/20 countries \u00b7 2023 snapshot</span>
        </div>
        <div class="ds-chips"><span class="ds-chip">port efficiency</span><span class="ds-chip">dwell time</span><span class="ds-chip">container ships</span></div>
      </div>

      <div class="ds-tile">
        <div class="ds-tile-head"><div class="ds-icon">\u2696\uFE0F</div><span class="ds-badge ds-badge-gov">GOV</span></div>
        <div class="ds-name">WGI</div>
        <div class="ds-cov">
          <div class="ds-dots"><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span><span class="ds-dot on"></span></div>
          <span class="ds-cov-label">20/20 countries \u00b7 2023 snapshot</span>
        </div>
        <div class="ds-chips"><span class="ds-chip">corruption</span><span class="ds-chip">rule of law</span><span class="ds-chip">reg quality</span></div>
      </div>

      <div class="ds-tile">
        <div class="ds-tile-head"><div class="ds-icon">\U0001F4C8</div><span class="ds-badge ds-badge-cost">COST</span></div>
        <div class="ds-name">BLS PPI \u2014 US Electronics</div>
        <div class="ds-cov">
          <div class="ds-bar-track"><div class="ds-bar-fill" style="width:88%"></div></div>
          <div class="ds-bar-labels"><span>multi-year</span><span>monthly</span></div>
        </div>
        <div class="ds-chips"><span class="ds-chip">IC</span><span class="ds-chip">transistors</span><span class="ds-chip">assemblies</span></div>
      </div>

      <div class="ds-tile">
        <div class="ds-tile-head"><div class="ds-icon">\U0001F4CA</div><span class="ds-badge ds-badge-cost">COST</span></div>
        <div class="ds-name">FRED PPI \u2014 MX/CA</div>
        <div class="ds-cov">
          <div class="ds-bar-track"><div class="ds-bar-fill" style="width:55%"></div></div>
          <div class="ds-bar-labels"><span>recent</span><span>monthly</span></div>
        </div>
        <div class="ds-chips"><span class="ds-chip">computer mfg</span><span class="ds-chip">electronics</span><span class="ds-chip">proxy</span></div>
      </div>

      <div class="ds-tile">
        <div class="ds-tile-head"><div class="ds-icon">\U0001F4C9</div><span class="ds-badge ds-badge-cost">COST</span></div>
        <div class="ds-name">FRED PPI \u2014 China/Asia</div>
        <div class="ds-cov">
          <div class="ds-bar-track"><div class="ds-bar-fill" style="width:60%"></div></div>
          <div class="ds-bar-labels"><span>recent</span><span>monthly</span></div>
        </div>
        <div class="ds-chips"><span class="ds-chip">China semi</span><span class="ds-chip">Asia proxy</span><span class="ds-chip">PPI</span></div>
      </div>

      <div class="ds-tile">
        <div class="ds-tile-head"><div class="ds-icon">\U0001F52C</div><span class="ds-badge ds-badge-cost">COST</span></div>
        <div class="ds-name">FRED PPI \u2014 US Semi</div>
        <div class="ds-cov">
          <div class="ds-bar-track"><div class="ds-bar-fill" style="width:65%"></div></div>
          <div class="ds-bar-labels"><span>recent</span><span>monthly</span></div>
        </div>
        <div class="ds-chips"><span class="ds-chip">advanced nodes</span><span class="ds-chip">CHIPS-Act</span><span class="ds-chip">semi</span></div>
      </div>

      <div class="ds-tile">
        <div class="ds-tile-head"><div class="ds-icon">\U0001F4B0</div><span class="ds-badge ds-badge-trd">TRADE</span></div>
        <div class="ds-name">USITC Tariff DB</div>
        <div class="ds-cov">
          <div class="ds-bar-track"><div class="ds-bar-fill" style="width:42%"></div></div>
          <div class="ds-bar-labels"><span>snapshot</span><span>2025</span></div>
        </div>
        <div class="ds-chips"><span class="ds-chip">HTS-8</span><span class="ds-chip">Ch 84/85/90</span><span class="ds-chip">tariff</span></div>
      </div>

      <div class="ds-tile">
        <div class="ds-tile-head"><div class="ds-icon">\U0001F6E2\uFE0F</div><span class="ds-badge ds-badge-trd">TRADE</span></div>
        <div class="ds-name">WB Commodity Prices</div>
        <div class="ds-cov">
          <div class="ds-bar-track"><div class="ds-bar-fill" style="width:100%"></div></div>
          <div class="ds-bar-labels"><span>1960</span><span>\u2192 2025</span></div>
        </div>
        <div class="ds-chips"><span class="ds-chip">oil</span><span class="ds-chip">copper</span><span class="ds-chip">aluminum</span></div>
      </div>

    </div>
  </div>
</div>

<div id="dp-panel-cleaning" class="dpanel">
  <div class="pclose" onclick="closeDp('cleaning')">\u2715</div>
  <div class="ph">Cleaning &amp; Normalization \u2014 4 Standard Transforms</div>
  <div class="psub">Raw supplier data unified to a consistent schema before load</div>

  <div class="gsec">
    <div class="gsec-n">Section 01</div>
    <div class="gsec-t">Transformation Cascade</div>
    <div class="cl-grid">

      <div class="cl-card">
        <div class="cl-card-icon">\U0001F310</div>
        <div class="cl-card-name">Country Normalization</div>
        <div class="cl-xform">
          <div class="cl-before">"United States"
"Korea, Rep."
"China, HK"</div>
          <div class="cl-arrow">\u2192</div>
          <div class="cl-after">USA
KOR
HKG</div>
        </div>
        <div class="cl-note">All country names \u2192 ISO-3 codes</div>
      </div>

      <div class="cl-card">
        <div class="cl-card-icon">\U0001F504</div>
        <div class="cl-card-name">Wide \u2192 Long Reshape</div>
        <div class="cl-xform">
          <div class="cl-before">yr_1996 yr_2000
 \u2026 yr_2023
(columns)</div>
          <div class="cl-arrow">\u2192</div>
          <div class="cl-after">year=1996
value=\u2026
year=2023
(rows)</div>
        </div>
        <div class="cl-note">Year columns melted into one <code style="font-family:'SF Mono',Menlo,Consolas,monospace;font-size:9px;color:#bbb;">year</code> column</div>
      </div>

      <div class="cl-card">
        <div class="cl-card-icon">\u2728</div>
        <div class="cl-card-name">Gap Interpolation</div>
        <div class="cl-xform">
          <div class="cl-before">[100, 102,
 NaN, NaN,
 109]</div>
          <div class="cl-arrow">\u2192</div>
          <div class="cl-after">[100, 102,
 104, 106,
 109]</div>
        </div>
        <div class="cl-note">Short gaps linear \u00b7 long gaps spline \u00b7 edges dropped</div>
      </div>

      <div class="cl-card">
        <div class="cl-card-icon">\U0001F9F9</div>
        <div class="cl-card-name">Column Filter + Rename</div>
        <div class="cl-xform">
          <div class="cl-before">"LPI Score"
"LPI Rank"
"LPI Cust"</div>
          <div class="cl-arrow">\u2192</div>
          <div class="cl-after">lpi_score
(rank fields
 dropped)</div>
        </div>
        <div class="cl-note">Drop rank fields \u00b7 snake_case all headers</div>
      </div>

    </div>
  </div>

  <div class="gsec">
    <div class="gsec-n">Section 02</div>
    <div class="gsec-t">Output Format</div>
    <div class="cl-chips">
      <span class="cl-chip">ISO-3 unified</span>
      <span class="cl-chip">snake_case</span>
      <span class="cl-chip">long format</span>
    </div>
    <div class="cl-caption">All 9 cleaned datasets \u2192 <code>cleaned_data/*.csv</code> \u2192 staged into Postgres</div>
  </div>
</div>

<div id="dp-panel-synth" class="dpanel">
  <div class="pclose" onclick="closeDp('synth')">\u2715</div>
  <div class="ph">Synthetic Generation \u2014 4-Stage Entity Factory</div>
  <div class="psub">Four notebooks build a fully synthetic, country-anchored procurement universe from cleaned public data</div>

  <div class="gsec">
    <div class="gsec-n">Section 01</div>
    <div class="gsec-t">Entity Pipeline</div>
    <div class="sn-pipeline-wrap">

      <div class="sn-edge-card sn-input">
        <div class="sn-edge-icon">\U0001F310</div>
        <div class="sn-edge-label">Cleaned Country Data</div>
        <div class="sn-edge-detail">LPI \u00b7 WGI<br>Tariffs \u00b7 PPI</div>
      </div>
      <div class="sn-connector"><div class="sn-conn-dots">\u22EF</div><div class="sn-conn-arrow">\u2192</div></div>

      <div class="sn-stage">
        <div class="sn-badge">1</div>
        <div class="sn-stage-icon">\U0001F3ED</div>
        <div class="sn-nb-name">01_suppliers.ipynb</div>
        <div class="sn-stat-num">89</div>
        <div class="sn-stat-label">suppliers \u00b7 21 countries</div>
        <div class="sn-entity-chip">Suppliers</div>
        <div class="sn-note">Lead time \u00b7 defect rate \u00b7 base price anchored to LPI / WGI / PPI</div>
      </div>
      <div class="sn-connector"><div class="sn-conn-dots">\u22EF</div><div class="sn-conn-arrow">\u2192</div></div>

      <div class="sn-stage">
        <div class="sn-badge">2</div>
        <div class="sn-stage-icon">\U0001F527</div>
        <div class="sn-nb-name">02_create_products.ipynb</div>
        <div class="sn-stat-num"><span class="sn-tilde">~</span>20</div>
        <div class="sn-stat-label">finished SKUs \u00b7 component families</div>
        <div class="sn-entity-chip">Products</div>
        <div class="sn-note">Finished-goods catalog + component families</div>
      </div>
      <div class="sn-connector"><div class="sn-conn-dots">\u22EF</div><div class="sn-conn-arrow">\u2192</div></div>

      <div class="sn-stage">
        <div class="sn-badge">3</div>
        <div class="sn-stage-icon">\U0001F517</div>
        <div class="sn-nb-name">03_link_suppliers_products.ipynb</div>
        <div class="sn-stat-num" style="font-size:22px;line-height:1.2;">S\u00d7P<br>Map</div>
        <div class="sn-stat-label">supplier-product map \u00b7 BOM</div>
        <div class="sn-entity-chip">BOM + Mapping</div>
        <div class="sn-note">Who supplies what \u00b7 BOM explosion backbone \u00b7 units-per-SKU</div>
      </div>
      <div class="sn-connector"><div class="sn-conn-dots">\u22EF</div><div class="sn-conn-arrow">\u2192</div></div>

      <div class="sn-stage">
        <div class="sn-badge">4</div>
        <div class="sn-stage-icon">\U0001F4CA</div>
        <div class="sn-nb-name">04_FinishedGoods_Demand.ipynb</div>
        <div class="sn-stat-num" style="font-size:20px;line-height:1.25;">W\u00d7F<br>\u00d7SKU</div>
        <div class="sn-stat-label">weekly \u00b7 facility \u00b7 SKU series</div>
        <div class="sn-entity-chip">Historical Demand</div>
        <div class="sn-note">Training data for HGB forecast model</div>
      </div>
      <div class="sn-connector"><div class="sn-conn-dots">\u22EF</div><div class="sn-conn-arrow">\u2192</div></div>

      <div class="sn-edge-card sn-output">
        <div class="sn-edge-icon">\u2705</div>
        <div class="sn-edge-label">LP-Ready Universe</div>
        <div class="sn-edge-detail">Fully linked<br>entity graph</div>
      </div>

    </div>
  </div>

  <div class="gsec">
    <div class="gsec-n">Section 02</div>
    <div class="gsec-t">Why Synthetic?</div>
    <div class="sn-why-card">
      <div class="sn-why-icon">\U0001F6E1\uFE0F</div>
      <div class="sn-why-body">
        <div class="sn-why-title">Why synthetic data?</div>
        <ul class="sn-why-bullets">
          <li>Real supplier rosters are NDA-protected and proprietary \u2014 no public dataset covers the supplier-product-facility graph needed for LP.</li>
          <li>Synthetic data anchored to real country-level public signals (LPI, WGI, tariffs, PPI) preserves economic realism without disclosing any firm's sourcing strategy.</li>
        </ul>
      </div>
    </div>
  </div>
</div>

<div id="dp-panel-sql" class="dpanel">
  <div class="pclose" onclick="closeDp('sql')">\u2715</div>
  <div class="ph">SQL Warehouse \u2014 11 Objects \u00b7 Strict Build Order</div>
  <div class="psub">PostgreSQL schema: 4 dimensions \u00b7 4 facts \u00b7 3 LP-ready views \u2014 load in the exact sequence below</div>

  <div class="gsec">
    <div class="gsec-n">Section 01</div>
    <div class="gsec-t">Schema Browser</div>
    <div class="sw-schema-grid">

      <div class="sw-family-col">
        <div class="sw-family-header">
          <span class="sw-family-icon">\U0001F4CB</span>
          <span class="sw-family-name">Dimensions</span>
          <span class="sw-family-badge sw-badge-dim">4</span>
        </div>
        <div class="sw-table-card sw-card-dim"><span class="sw-table-name">dim_supplier</span><span class="sw-table-grain">one row per supplier</span></div>
        <div class="sw-table-card sw-card-dim"><span class="sw-table-name">dim_product</span><span class="sw-table-grain">one row per component/SKU</span></div>
        <div class="sw-table-card sw-card-dim"><span class="sw-table-name">dim_bom</span><span class="sw-table-grain">SKU\u2192component bridge</span></div>
        <div class="sw-table-card sw-card-dim"><span class="sw-table-name">dim_forecast_run</span><span class="sw-table-grain">forecast batch metadata</span></div>
      </div>

      <div class="sw-family-col">
        <div class="sw-family-header">
          <span class="sw-family-icon">\U0001F4CA</span>
          <span class="sw-family-name">Facts</span>
          <span class="sw-family-badge sw-badge-fact">4</span>
        </div>
        <div class="sw-table-card sw-card-fact"><span class="sw-table-name">fact_semiconductor_demand</span><span class="sw-table-grain">historical weekly demand</span></div>
        <div class="sw-table-card sw-card-fact"><span class="sw-table-name">fact_supplier_product_profile</span><span class="sw-table-grain">price/quality per supplier</span></div>
        <div class="sw-table-card sw-card-fact"><span class="sw-table-name">fact_inventory_policy</span><span class="sw-table-grain">safety stock + base-stock per fac\u00d7product</span></div>
        <div class="sw-table-card sw-card-fact"><span class="sw-table-name">fact_component_inventory_history</span><span class="sw-table-grain">weekly benchmark inventory</span></div>
      </div>

      <div class="sw-family-col">
        <div class="sw-family-header">
          <span class="sw-family-icon">\U0001F50D</span>
          <span class="sw-family-name">Views</span>
          <span class="sw-family-badge sw-badge-view">3</span>
        </div>
        <div class="sw-table-card sw-card-view"><span class="sw-table-name">vw_supplier_complete_profile</span><span class="sw-table-grain">canonical LP supplier input</span></div>
        <div class="sw-table-card sw-card-view"><span class="sw-table-name">vw_component_requirement_lp</span><span class="sw-table-grain">horizon demand for LP</span></div>
        <div class="sw-table-card sw-card-view"><span class="sw-table-name">vw_procurement_requirement</span><span class="sw-table-grain">weekly trigger signal</span></div>
      </div>

    </div>
  </div>

  <div class="gsec">
    <div class="gsec-n">Section 02</div>
    <div class="gsec-t">Build Order</div>
    <div class="sw-ladder">
      <div class="sw-ladder-line"></div>

      <div class="sw-ladder-step"><div class="sw-step-num">1</div><div class="sw-step-body"><span class="sw-step-file">dimensions.sql</span><span class="sw-step-type sw-type-ddl">DDL</span></div></div>
      <div class="sw-ladder-step"><div class="sw-step-num">2</div><div class="sw-step-body"><span class="sw-step-file">facts.sql</span><span class="sw-step-type sw-type-ddl">DDL</span></div></div>
      <div class="sw-ladder-step"><div class="sw-step-num">3</div><div class="sw-step-body"><span class="sw-step-file">load/stage.sql</span><span class="sw-step-type sw-type-stage">STAGING DDL</span></div></div>
      <div class="sw-ladder-step"><div class="sw-step-num">4</div><div class="sw-step-body"><span class="sw-step-file">load/copy_staging.sql</span><span class="sw-step-type sw-type-data">DATA LOAD</span></div></div>
      <div class="sw-ladder-step"><div class="sw-step-num">5</div><div class="sw-step-body"><span class="sw-step-file">load/load_dimensions.sql</span><span class="sw-step-type sw-type-data">DATA LOAD</span></div></div>
      <div class="sw-ladder-step"><div class="sw-step-num">6</div><div class="sw-step-body"><span class="sw-step-file">load/load_facts.sql</span><span class="sw-step-type sw-type-data">DATA LOAD</span></div></div>
      <div class="sw-ladder-step"><div class="sw-step-num">7</div><div class="sw-step-body"><span class="sw-step-file">load/load_bom.sql</span><span class="sw-step-type sw-type-data">DATA LOAD</span></div></div>
      <div class="sw-ladder-step"><div class="sw-step-num">8</div><div class="sw-step-body"><span class="sw-step-file">views.sql</span><span class="sw-step-type sw-type-views">VIEWS</span></div></div>

      <div class="sw-ladder-warn"><i class="sw-warn-icon">\u26A0</i>Out-of-order execution breaks foreign keys. See <span class="sw-warn-code">sql/README.md</span> for full commands.</div>
    </div>
  </div>
</div>


<script>
var canvas = document.getElementById("c");
var ctx = canvas.getContext("2d");
var tip = document.getElementById("tip");
var DPR = window.devicePixelRatio || 1;
var TAU = Math.PI * 2;
var W, H;

function resize() {
  W = canvas.parentElement.clientWidth || 1000;
  H = 1150;
  canvas.width = W * DPR;
  canvas.height = H * DPR;
  canvas.style.width = W + "px";
  canvas.style.height = H + "px";
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
}
resize();

// Phase descriptions for tooltips
var INFO = {
  sources: {desc:"9 public datasets covering logistics, governance, tariffs, and price indices. Each normalized to ISO-3 country codes.", tools:["World Bank LPI (logistics, 20 countries)","World Governance Indicators (WGI)","UNCTAD Port Calls (container ships)","USITC Tariff DB (HTS-8, Ch. 84/85/90)","BLS PPI (US electronics)","FRED PPI \u00d7 3 (MX/CA, China, US semi)","World Bank Commodity Prices"]},
  cleaning: {desc:"Standardization pipeline. Wide-to-long reshape, missing-value interpolation, country/product key unification.", tools:["scripts/data_cleaning/00_clean_structured_data.ipynb","ISO-3 country normalization","Linear + spline interpolation (PPI gaps)","Output: cleaned_data/*.csv"]},
  synthesis: {desc:"Synthetic supplier universe anchored to real country risk and cost signals. Generates 89 suppliers across 21 countries.", tools:["01_suppliers.ipynb","02_create_products.ipynb","03_link_suppliers_products.ipynb","04_FinishedGoods_Demand_Table.ipynb"]},
  sql: {desc:"PostgreSQL warehouse. Strict build order: dimensions \u2192 facts \u2192 staging \u2192 loads \u2192 views.", tools:["dim_supplier, fact_supplier_product_profile","fact_semiconductor_demand, dim_bom","sql/load/ (6 scripts, strict order)","sql/views.sql (LP-ready aggregations)"]},
  forecast: {desc:"HGB demand model. Predicts finished-good demand per facility \u00d7 SKU \u00d7 week for a 20-week horizon.", tools:["forecasting/run_pipeline.py","Output: fact_semiconductor_demand_forecast","Grain: forecast_run \u00d7 facility \u00d7 SKU \u00d7 week"]},
  inventory: {desc:"Base-stock policy. Computes safety stock and weekly procurement triggers via rolling depletion.", tools:["inventory/run_inventory.py","fact_inventory_policy (SS + S targets)","vw_procurement_requirement (weekly trigger)","vw_component_requirement_lp (LP input)"]},
  lp: {desc:"PuLP/CBC solver. Allocates procurement across eligible suppliers to minimize risk-adjusted cost.", tools:["optimization/run_lp_optimization.py","Inputs: vw_component_requirement_lp + vw_supplier_complete_profile","Objective: min \u03a3 cost \u00d7 (1 + \u03bb_risk \u00d7 risk)","Constraints: demand, compliance, diversification"]},
};

// ── Node layout ──
var NW = 345, NH = 78;       // main pipeline nodes
var SW = 225, SH = 66;       // side-by-side parallel nodes (row 4)
var TW = 210, TH = 60;       // terminal node
var RG = 140;                // row gap
var cx = W / 2;

// Row Y positions
var RY = {
  sources: 70,
  cleaning: 70 + RG,
  synthesis: 70 + RG * 2,
  sql: 70 + RG * 3,
  parallel: 70 + RG * 4,
  lp: 70 + RG * 5,
  output: 70 + RG * 6,
};

// Step number badges
var STEP_BADGES = {
  data_sources:"1", cleaning:"2", synthesis:"3", sql_warehouse:"4",
  forecast:"5a", inventory:"5b", lp:"6", output:null,
};

var nodes = [
  {id:"data_sources", label:"Public Data Sources", cx:cx, cy:RY.sources, w:NW, h:NH, key:"sources"},
  {id:"cleaning", label:"Cleaning & Normalization", cx:cx, cy:RY.cleaning, w:NW, h:NH, key:"cleaning"},
  {id:"synthesis", label:"Synthetic Generation", cx:cx, cy:RY.synthesis, w:NW, h:NH, key:"synthesis"},
  {id:"sql_warehouse", label:"SQL Warehouse", cx:cx, cy:RY.sql, w:NW, h:NH, key:"sql"},
  {id:"forecast", label:"Forecast", cx:cx-(SW/2+30), cy:RY.parallel, w:SW, h:SH, key:"forecast"},
  {id:"inventory", label:"Inventory Policy", cx:cx+(SW/2+30), cy:RY.parallel, w:SW, h:SH, key:"inventory"},
  {id:"lp", label:"LP Optimization", cx:cx, cy:RY.lp, w:NW, h:NH, key:"lp"},
  {id:"output", label:"Procurement Plan", cx:cx, cy:RY.output, w:TW, h:TH, key:null},
];
nodes.forEach(function(n) { n.x = n.cx - n.w/2; n.y = n.cy - n.h/2; });

var nodeMap = {};
nodes.forEach(function(n) { nodeMap[n.id] = n; });

var rowOf = {
  data_sources:0, cleaning:1, synthesis:2, sql_warehouse:3,
  forecast:4, inventory:4, lp:5, output:6,
};

var EDGES = [
  ["data_sources","cleaning"],
  ["cleaning","synthesis"],
  ["synthesis","sql_warehouse"],
  ["sql_warehouse","forecast"],
  ["sql_warehouse","inventory"],
  ["forecast","lp"],
  ["inventory","lp"],
  ["lp","output"],
];

// Critical path: all edges are on the critical path
var CRITICAL_PATH_EDGES = {};
EDGES.forEach(function(e) { CRITICAL_PATH_EDGES[e[0]+"|"+e[1]] = true; });

var edges = EDGES.map(function(e) {
  var a = nodeMap[e[0]], b = nodeMap[e[1]];
  if (!a || !b) return null;
  var isCritical = CRITICAL_PATH_EDGES[e[0]+"|"+e[1]] || false;
  return {x1:a.cx, y1:a.cy+a.h/2, x2:b.cx, y2:b.cy-b.h/2, fromRow:rowOf[e[0]]||0, horiz:false, critical:isCritical};
}).filter(Boolean);

// Particles (2 per edge)
var particles = [];
edges.forEach(function(e) {
  for (var i = 0; i < 2; i++) {
    particles.push({edge:e, offset:i/2, speed:0.3+Math.random()*0.25});
  }
});

function drawRR(x,y,w,h,r) {
  ctx.beginPath();
  ctx.moveTo(x+r,y); ctx.lineTo(x+w-r,y); ctx.arcTo(x+w,y,x+w,y+r,r);
  ctx.lineTo(x+w,y+h-r); ctx.arcTo(x+w,y+h,x+w-r,y+h,r);
  ctx.lineTo(x+r,y+h); ctx.arcTo(x,y+h,x,y+h-r,r);
  ctx.lineTo(x,y+r); ctx.arcTo(x,y,x+r,y,r); ctx.closePath();
}
function clamp(v,a,b) { return Math.max(a,Math.min(b,v)); }
function easeOut(t) { return 1-Math.pow(1-t,3); }

// Click-to-expand wiring
var DP_EXPANDABLE = {
  data_sources:  {panel:"dp-panel-sources",  tip:"Click to see all 9 datasets grouped by domain"},
  cleaning:      {panel:"dp-panel-cleaning", tip:"Click to see before/after transforms"},
  synthesis:     {panel:"dp-panel-synth",    tip:"Click to see 4-notebook generation chain"},
  sql_warehouse: {panel:"dp-panel-sql",      tip:"Click to see the full schema + build order"},
};
function closeDp(which) {
  var map = {sources:"dp-panel-sources", cleaning:"dp-panel-cleaning",
             synth:"dp-panel-synth", sql:"dp-panel-sql"};
  var id = map[which];
  if (id) document.getElementById(id).style.display = "none";
}
function closeAllDp() {
  ["dp-panel-sources","dp-panel-cleaning","dp-panel-synth","dp-panel-sql"]
    .forEach(function(id) { document.getElementById(id).style.display = "none"; });
}
document.addEventListener("keydown", function(e) { if (e.key === "Escape") closeAllDp(); });

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
  canvas.style.cursor = (hoverNode && DP_EXPANDABLE[hoverNode.id]) ? "pointer" : "default";
  if (hoverNode) {
    var key = hoverNode.key;
    var html = '<div class="tl">' + hoverNode.label + '</div>';
    if (key && INFO[key]) {
      html += '<div class="td">' + INFO[key].desc + '</div>';
      INFO[key].tools.forEach(function(t) { html += '<div class="tt">' + t + '</div>'; });
    }
    if (hoverNode.id === "output") html += '<div class="td">Final supplier allocation with cost, risk, and executive summary.</div>';
    if (DP_EXPANDABLE[hoverNode.id]) html += '<div class="td" style="color:#76b900;font-weight:600;">\u25B6 ' + DP_EXPANDABLE[hoverNode.id].tip + '</div>';
    tip.innerHTML = html;
    tip.style.display = "block";
    var tx = mx + 14, ty = my - 10;
    if (tx + 340 > W) tx = mx - 350;
    if (ty + 200 > H) ty = my - 200;
    tip.style.left = tx + "px";
    tip.style.top = ty + "px";
  } else { tip.style.display = "none"; }
});
canvas.addEventListener("mouseleave", function() { tip.style.display = "none"; });
canvas.addEventListener("click", function(evt) {
  var rect = canvas.getBoundingClientRect();
  var mx = evt.clientX - rect.left, my = evt.clientY - rect.top;
  for (var i = 0; i < nodes.length; i++) {
    var n = nodes[i];
    if (mx >= n.x && mx <= n.x+n.w && my >= n.y && my <= n.y+n.h) {
      if (DP_EXPANDABLE[n.id]) {
        document.getElementById(DP_EXPANDABLE[n.id].panel).style.display = "block";
        tip.style.display = "none";
      }
      break;
    }
  }
});

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

  // "PARALLEL" label above row 4 (forecast + inventory)
  var plA = easeOut(clamp((progress-0.15)*3,0,1));
  ctx.save(); ctx.globalAlpha = plA*0.4;
  ctx.font = "700 11px Inter,sans-serif"; ctx.fillStyle = "#76b900";
  ctx.textAlign = "center";
  ctx.fillText("PARALLEL \u2014 DEMAND + INVENTORY SIGNAL", cx, RY.parallel - SH/2 - 16);
  ctx.restore();

  // Edges
  edges.forEach(function(e) {
    var delay = e.fromRow * 0.08;
    var ep = easeOut(clamp((progress - delay) / 0.25, 0, 1));
    if (ep <= 0) return;
    ctx.beginPath();
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
    ctx.strokeStyle = e.critical ? "rgba(118,185,0,0.45)" : "rgba(118,185,0,0.3)";
    ctx.lineWidth = e.critical ? 2.5 : 1.5;
    ctx.stroke();
  });

  // Flowing particles
  if (progress > 0.25) {
    var pA = clamp((progress-0.25)/0.15, 0, 1);
    particles.forEach(function(p) {
      var e = p.edge;
      var cycle = 2200 / p.speed;
      var t = ((elapsed + p.offset*cycle) % cycle) / cycle;
      var my = (e.y1+e.y2)/2;
      var u = 1-t;
      var px = u*u*u*e.x1 + 3*u*u*t*e.x1 + 3*u*t*t*e.x2 + t*t*t*e.x2;
      var py = u*u*u*e.y1 + 3*u*u*t*my + 3*u*t*t*my + t*t*t*e.y2;
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

    ctx.font = "700 " + (n.h < 68 ? "13" : "16") + "px Inter,sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillStyle = isTerminal ? "#999" : "#fff";
    ctx.fillText(n.label.toUpperCase(), n.cx, n.cy);

    // Step number badge
    var badge = STEP_BADGES[n.id];
    if (badge) {
      var bx = n.x + 14;
      var by = n.y + 14;
      var br = 12;
      ctx.beginPath();
      ctx.arc(bx, by, br, 0, TAU);
      ctx.fillStyle = "#76b900";
      ctx.fill();
      ctx.font = "700 11px Inter,sans-serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillStyle = "#000";
      ctx.fillText(badge, bx, by);
    }

    // Pulsing "+" indicator for expandable nodes
    if (DP_EXPANDABLE && DP_EXPANDABLE[n.id]) {
      var epulse = 0.6 + 0.4 * Math.sin(elapsed/400);
      var ebx = n.x + n.w - 16;
      var eby = n.y + n.h - 16;
      var ebr = 12;
      ctx.beginPath();
      ctx.arc(ebx, eby, ebr, 0, TAU);
      ctx.fillStyle = "rgba(118,185,0," + (0.85*epulse) + ")";
      ctx.fill();
      ctx.strokeStyle = "#76b900"; ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.font = "700 15px Inter,sans-serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillStyle = "#0A1F17";
      ctx.fillText("+", ebx, eby);
    }

    ctx.restore();
  });

  // Legend (bottom-left)
  if (progress > 0.7) {
    var legA = clamp((progress-0.7)/0.2, 0, 1);
    ctx.save(); ctx.globalAlpha = legA;
    var legX = 24;
    var legY = H - 78;
    var legSpacing = 22;
    ctx.font = "400 11px Inter,sans-serif";
    ctx.textBaseline = "middle";

    drawRR(legX, legY - 5, 14, 10, 2);
    ctx.strokeStyle = "#76b900"; ctx.lineWidth = 2; ctx.setLineDash([]);
    ctx.stroke();
    ctx.fillStyle = "#888"; ctx.textAlign = "left";
    ctx.fillText("Pipeline stage", legX + 20, legY);

    drawRR(legX, legY + legSpacing - 5, 14, 10, 2);
    ctx.strokeStyle = "#555"; ctx.lineWidth = 1; ctx.setLineDash([]);
    ctx.stroke();
    ctx.fillStyle = "#888";
    ctx.fillText("Final output", legX + 20, legY + legSpacing);

    ctx.beginPath();
    ctx.moveTo(legX, legY + legSpacing*2);
    ctx.lineTo(legX + 14, legY + legSpacing*2);
    ctx.strokeStyle = "#76b900"; ctx.lineWidth = 1.5; ctx.setLineDash([]);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(legX + 7, legY + legSpacing*2, 2.5, 0, TAU);
    ctx.fillStyle = "#76b900"; ctx.fill();
    ctx.fillStyle = "#888";
    ctx.fillText("Data flow", legX + 20, legY + legSpacing*2);

    ctx.restore();
  }

  // Footer
  if (progress > 0.8) {
    var ba = clamp((progress-0.8)/0.2, 0, 1);
    ctx.save(); ctx.globalAlpha = ba;
    ctx.font = "600 11px Inter,sans-serif";
    ctx.textAlign = "center"; ctx.fillStyle = "#555";
    ctx.fillText("HOVER NODES FOR DETAILS", cx, H - 14);
    ctx.restore();
  }

  requestAnimationFrame(draw);
}
requestAnimationFrame(draw);
</script></body></html>'''

    components.html(dp_html, height=1160)


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
                    max-width:640px; margin:0 auto 2rem; line-height:1.65;
                    white-space:nowrap;">
            Analyzing suppliers, pricing signals, and logistics with real-time risk assessment.
          </p>
        </div>
        """, unsafe_allow_html=True)

        # Intelligence panel
        st.markdown("""
        <div style="background:#0A1F17;
                    border:1px solid #333333; border-radius:2px;
                    padding:1.75rem 2rem; margin-bottom:1.5rem;">
          <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:1.5rem; margin-bottom:1.5rem;">
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
            ("Risk Agent — Geopolitical",
             "Are there any recent geopolitical risks affecting semiconductor supply chains in East Asia?"),
            ("Multi-Agent — Internal × External",
             "Show me where and when we need to trigger procurement in the upcoming horizon, "
             "and scan recent news for any semiconductor supply chain disruptions or tariff changes."),
        ]
        st.markdown("<div class='suggestion-row'>", unsafe_allow_html=True)
        cols = st.columns(len(_SUGGESTIONS))
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
                        + section_header("·", "03 — Visualizations", "#76b900")
                        + "</div>",
                        unsafe_allow_html=True,
                    )
                    render_charts(chart_results)
                if msg.get("summary"):
                    st.markdown(msg["summary"])
        if msg.get("has_trace") and assistant_index < len(traces):
            show_trace_fn(traces[assistant_index])
            assistant_index += 1
