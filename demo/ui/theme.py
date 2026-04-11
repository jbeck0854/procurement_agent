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
    "background:rgba(36,57,48,0.6); backdrop-filter:blur(20px);"
    "border:1px solid rgba(61,74,57,0.15); border-radius:0.5rem;"
    "padding:1.25rem 1.5rem; margin-bottom:0.875rem;"
    "box-shadow:0 0 40px rgba(90,235,86,0.06);"
)


def section_header(icon: str, label: str, accent: str = "#879580") -> str:
    """Return HTML for a styled section header inside a glass card."""
    return (
        f"<div style='display:flex; align-items:center; gap:0.5rem; margin-bottom:0.875rem;'>"
        f"<span style='color:{accent}; font-size:0.9rem;'>{icon}</span>"
        f"<p style='font-family:Inter,sans-serif; font-size:0.58rem; letter-spacing:0.15em;"
        f"text-transform:uppercase; color:#879580; margin:0;'>{label}</p>"
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
        font-family: 'Manrope', sans-serif !important;
        color: #D0E8DA !important;
    }
    .stApp::after {
        content: '';
        position: fixed;
        bottom: 0; right: 0;
        width: 320px; height: 320px;
        background: radial-gradient(ellipse at bottom right, rgba(170,248,255,0.035), transparent 70%);
        pointer-events: none;
        z-index: 0;
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
        border-right: 1px solid rgba(61,74,57,0.15) !important;
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
        background: linear-gradient(135deg, #AEFFA0, #5AEB56) !important;
        color: #002202 !important;
        font-family: 'Space Grotesk', sans-serif !important;
        font-weight: 700 !important;
        font-size: 0.75rem !important;
        letter-spacing: 0.04em !important;
        text-transform: uppercase !important;
        border-radius: 0.125rem !important;
        border: none !important;
        width: 100% !important;
        padding: 0.6rem 1rem !important;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        box-shadow: 0 0 18px rgba(90,235,86,0.4) !important;
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
        color: #D0E8DA !important;
    }
    p, li, .stMarkdown p {
        font-family: 'Manrope', sans-serif !important;
        color: #D0E8DA !important;
        line-height: 1.65 !important;
    }

    /* ── Chat messages ── */
    .stChatMessage {
        background: rgba(36,57,48,0.45) !important;
        border: 1px solid rgba(61,74,57,0.15) !important;
        border-radius: 0.375rem !important;
        backdrop-filter: blur(10px) !important;
        margin-bottom: 0.75rem !important;
    }
    .stChatMessage[data-testid="stChatMessageUser"] {
        background: rgba(90,235,86,0.05) !important;
        border-color: rgba(90,235,86,0.12) !important;
    }

    /* ── Chat input ── */
    [data-testid="stChatInput"] {
        background: rgba(36,57,48,0.6) !important;
        border: 1px solid rgba(90,235,86,0.2) !important;
        border-radius: 2rem !important;
        backdrop-filter: blur(20px) !important;
        box-shadow: 0 0 30px rgba(90,235,86,0.08), inset 0 0 10px rgba(90,235,86,0.04) !important;
    }
    [data-testid="stChatInput"]:focus-within {
        border-color: rgba(90,235,86,0.45) !important;
        box-shadow: 0 0 40px rgba(90,235,86,0.14) !important;
    }
    [data-testid="stChatInput"] textarea,
    [data-testid="stChatInputTextArea"] textarea {
        background: transparent !important;
        color: #D0E8DA !important;
        font-family: 'Manrope', sans-serif !important;
        font-size: 0.95rem !important;
    }
    [data-testid="stChatInput"] button[data-testid="stChatInputSubmitButton"],
    [data-testid="stChatInput"] button {
        background: linear-gradient(135deg, #AEFFA0, #5AEB56) !important;
        color: #002202 !important;
        border-radius: 50% !important;
        border: none !important;
        box-shadow: 0 0 14px rgba(90,235,86,0.35) !important;
    }

    /* ── Primary buttons ── */
    .stButton > button {
        background: linear-gradient(135deg, #AEFFA0, #5AEB56) !important;
        color: #002202 !important;
        -webkit-text-fill-color: #002202 !important;
        border: none !important;
        border-radius: 0.125rem !important;
        font-family: 'Space Grotesk', sans-serif !important;
        font-weight: 700 !important;
        letter-spacing: 0.04em !important;
        text-transform: uppercase !important;
        font-size: 0.75rem !important;
        padding: 0.6rem 1.5rem !important;
        transition: box-shadow 0.2s ease, transform 0.15s ease !important;
    }
    .stButton > button p,
    .stButton > button span,
    .stButton > button div {
        color: #002202 !important;
        -webkit-text-fill-color: #002202 !important;
    }
    .stButton > button:hover {
        box-shadow: 0 0 20px rgba(90,235,86,0.4) !important;
        transform: scale(1.02) !important;
    }
    .stButton > button:active {
        transform: scale(0.97) !important;
    }

    /* ── Text input ── */
    .stTextInput > div > div > input {
        background: transparent !important;
        border: none !important;
        border-bottom: 1px solid #879580 !important;
        border-radius: 0 !important;
        color: #D0E8DA !important;
        font-family: 'Manrope', sans-serif !important;
        font-size: 0.9rem !important;
        padding: 0.4rem 0 !important;
        box-shadow: none !important;
        outline: none !important;
    }
    .stTextInput > div > div > input:focus {
        border-bottom: 1px solid #5AEB56 !important;
        box-shadow: 0 2px 0 -1px rgba(90,235,86,0.5) !important;
    }
    .stTextInput > div > div > input::placeholder {
        color: rgba(135,149,128,0.6) !important;
    }
    .stTextInput label,
    .stTextInput > label {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.6rem !important;
        letter-spacing: 0.15em !important;
        text-transform: uppercase !important;
        color: #879580 !important;
    }

    /* ── Expander ── */
    .stExpander {
        background: rgba(15,35,27,0.55) !important;
        border: 1px solid rgba(61,74,57,0.15) !important;
        border-radius: 0.25rem !important;
        margin-top: 0.5rem !important;
    }
    .stExpander details summary {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.65rem !important;
        letter-spacing: 0.15em !important;
        text-transform: uppercase !important;
        color: #879580 !important;
    }
    .stExpander details summary:hover { color: #AEFFA0 !important; }
    .stExpander details summary svg { color: #879580 !important; }

    /* ── Metrics ── */
    [data-testid="metric-container"] {
        background: rgba(25,46,37,0.5) !important;
        border: 1px solid rgba(61,74,57,0.15) !important;
        border-radius: 0.25rem !important;
        padding: 0.7rem 1rem !important;
    }
    [data-testid="metric-container"] label {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.55rem !important;
        letter-spacing: 0.15em !important;
        text-transform: uppercase !important;
        color: #879580 !important;
    }
    [data-testid="stMetricValue"] {
        font-family: 'Space Grotesk', sans-serif !important;
        color: #AEFFA0 !important;
        font-size: 1.3rem !important;
        font-weight: 700 !important;
    }

    /* ── Code blocks ── */
    .stCode, .stCodeBlock, pre, code {
        background: rgba(0,18,10,0.85) !important;
        border: 1px solid rgba(61,74,57,0.2) !important;
        border-radius: 0.25rem !important;
        font-size: 0.78rem !important;
        color: #AEFFA0 !important;
    }
    pre { padding: 0.875rem !important; }

    /* ── Divider ── */
    hr { border-color: rgba(61,74,57,0.2) !important; margin: 1rem 0 !important; }

    /* ── Spinner ── */
    [data-testid="stSpinner"] > div > div {
        border-top-color: #5AEB56 !important;
    }

    /* ── Caption ── */
    .stCaptionContainer,
    [data-testid="stCaptionContainer"],
    small, .caption {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.6rem !important;
        letter-spacing: 0.12em !important;
        text-transform: uppercase !important;
        color: #879580 !important;
    }

    /* ── Info box ── */
    [data-testid="stAlert"],
    .stInfo, .stSuccess, .stWarning {
        background: rgba(36,57,48,0.6) !important;
        border: 1px solid rgba(90,235,86,0.18) !important;
        color: #BCCBB4 !important;
        border-radius: 0.25rem !important;
    }

    /* ── Scrollbar ── */
    ::-webkit-scrollbar { width: 4px; height: 4px; }
    ::-webkit-scrollbar-track { background: #03170F; }
    ::-webkit-scrollbar-thumb { background: rgba(90,235,86,0.25); border-radius: 2px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(90,235,86,0.45); }

    /* ── Inline result blocks (glass cards) ── */
    .result-label {
        font-family: 'Inter', sans-serif;
        font-size: 0.6rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #879580;
        margin: 0.75rem 0 0.3rem;
    }
    .result-pre {
        background: rgba(0,26,10,0.5);
        border-radius: 0.25rem;
        padding: 0.75rem 1rem;
        font-family: 'Inter', monospace;
        font-size: 0.78rem;
        color: #AEFFA0;
        white-space: pre-wrap;
        word-break: break-word;
        overflow-x: auto;
        max-height: 220px;
        overflow-y: auto;
        margin: 0 0 0.5rem;
    }
    .summary-body p, .summary-body li {
        font-family: 'Manrope', sans-serif !important;
        color: #D0E8DA !important;
        font-size: 0.9rem !important;
        line-height: 1.7 !important;
    }
    .summary-body h2, .summary-body h3 {
        font-family: 'Space Grotesk', sans-serif !important;
        color: #AEFFA0 !important;
        margin-top: 1rem !important;
    }

    /* ── Suggestion chips ── */
    .suggestion-row .stButton > button {
        background: rgba(36,57,48,0.7) !important;
        border: 1px solid rgba(90,235,86,0.18) !important;
        border-radius: 0.375rem !important;
        color: #BCCBB4 !important;
        -webkit-text-fill-color: #BCCBB4 !important;
        font-family: 'Manrope', sans-serif !important;
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
        color: #BCCBB4 !important;
        -webkit-text-fill-color: #BCCBB4 !important;
        font-size: 0.8rem !important;
        font-weight: 500 !important;
        text-transform: none !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }
    .suggestion-row .stButton > button:hover {
        border-color: rgba(90,235,86,0.45) !important;
        background: rgba(36,57,48,0.95) !important;
        box-shadow: 0 0 14px rgba(90,235,86,0.12) !important;
        transform: none !important;
    }
    .suggestion-row .stButton > button:hover p,
    .suggestion-row .stButton > button:hover span,
    .suggestion-row .stButton > button:hover div {
        color: #AEFFA0 !important;
        -webkit-text-fill-color: #AEFFA0 !important;
    }
    </style>
    """, unsafe_allow_html=True)


# ── Fixed top header bar ─────────────────────────────────────────────────────

def render_header():
    """Render a fixed top navigation bar with logo and brand name."""
    logo_html = (
        f"<img src='data:image/png;base64,{LOGO_B64}' "
        f"style='height:32px; width:auto; object-fit:contain; background:transparent;'/>"
        if LOGO_B64 else
        "<span style='font-size:1.4rem; color:#5AEB56;'>⬡</span>"
    )
    st.markdown(f"""
    <div style="position:fixed; top:0; left:0; right:0; z-index:999;
                background:rgba(3,23,15,0.85); backdrop-filter:blur(20px);
                border-bottom:1px solid rgba(61,74,57,0.15);
                display:flex; align-items:center; justify-content:flex-start;
                padding:0.65rem 1.5rem; height:3.5rem;">
      <div style="display:flex; align-items:center; gap:0.75rem;">
        {logo_html}
        <span style="font-family:'Space Grotesk',sans-serif; font-size:0.9rem; font-weight:800;
                     color:#5AEB56; letter-spacing:0.04em; text-transform:uppercase;">
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
        f"style='height:64px; width:auto; object-fit:contain; background:transparent;'/>"
        if LOGO_B64 else
        "<span style='font-size:1.2rem; color:#5AEB56; line-height:1;'>⬡</span>"
    )
    st.markdown(f"""
    <div style="padding:1.25rem 1.25rem 1rem; border-bottom:1px solid rgba(61,74,57,0.15);">
      <div style="display:flex; align-items:center; gap:0.55rem; margin-bottom:0.35rem;">
        {logo_html}
        <span style="font-family:'Space Grotesk',sans-serif; font-size:0.95rem; font-weight:800;
                     color:#5AEB56; letter-spacing:-0.01em; text-transform:uppercase;">
          Procurement Pilot
        </span>
      </div>
      <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.18em;
                text-transform:uppercase; color:#879580; margin:0;">
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
        padding: 0.6rem 1.25rem !important;
        width: 100% !important;
        text-align: left !important;
        font-family: 'Manrope', sans-serif !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        letter-spacing: 0 !important;
        text-transform: none !important;
        margin-bottom: 2px !important;
        transition: background 0.15s !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button p,
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button span,
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button div {
        color: #879580 !important;
        -webkit-text-fill-color: #879580 !important;
        font-family: 'Manrope', sans-serif !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover {
        background: #243930 !important;
        box-shadow: none !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover p,
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover span,
    section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover div {
        color: #D0E8DA !important;
        -webkit-text-fill-color: #D0E8DA !important;
    }
    </style>
    """, unsafe_allow_html=True)

    view = st.session_state.current_view

    # Current Sourcing nav item
    if view == "chat":
        st.markdown("""
        <div style="display:flex; align-items:center; gap:0.7rem; padding:0.6rem 1.25rem;
                    background:#1A2E24; border-right:3px solid #5AEB56; margin-bottom:2px;
                    font-family:'Manrope',sans-serif; font-size:0.85rem; font-weight:600;
                    color:#5AEB56;">
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
        <div style="display:flex; align-items:center; gap:0.7rem; padding:0.6rem 1.25rem;
                    background:#1A2E24; border-right:3px solid #5AEB56; margin-bottom:2px;
                    font-family:'Manrope',sans-serif; font-size:0.85rem; font-weight:600;
                    color:#5AEB56;">
          <span>◷</span><span>Session History</span>
        </div>""", unsafe_allow_html=True)
    else:
        if st.button(history_label, key="nav_history"):
            st.session_state.current_view = "history"
            st.session_state.viewing_session = None
            st.rerun()

    # Decorative nav items
    for icon, label in [("◈", "Supplier Scorecard"), ("◷", "Risk Monitor")]:
        st.markdown(f"""
        <div style="display:flex; align-items:center; gap:0.7rem; padding:0.6rem 1.25rem;
                    margin-bottom:2px; font-family:'Manrope',sans-serif; font-size:0.85rem;
                    font-weight:500; color:#879580;">
          <span>{icon}</span><span>{label}</span>
        </div>""", unsafe_allow_html=True)

    # Export PDF button
    if st.button("↓  Export Session as PDF", key="export_pdf"):
        st.components.v1.html(
            "<script>window.parent.print();</script>",
            height=0,
        )

    st.markdown("""
    <div style="margin-top:2rem; padding:1rem 1.25rem 0;
                border-top:1px solid rgba(61,74,57,0.15);">
      <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.15em;
                text-transform:uppercase; color:rgba(61,74,57,0.9); margin-bottom:0.4rem;
                cursor:pointer;">
        Technical Docs
      </p>
      <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.15em;
                text-transform:uppercase; color:rgba(61,74,57,0.6); margin:0;">
        V1.0.0-BETA
      </p>
    </div>
    """, unsafe_allow_html=True)


# ── Landing page ─────────────────────────────────────────────────────────────

def render_landing():
    """Render the landing page with metrics panel and suggestion chips."""
    # Top-left corner glow
    st.markdown("""
    <div style="position:fixed; top:0; left:0; width:200px; height:200px;
                background:radial-gradient(ellipse at top left, rgba(90,235,86,0.07), transparent 70%);
                pointer-events:none; z-index:0;"></div>
    """, unsafe_allow_html=True)

    _, center, _ = st.columns([1, 3, 1])
    with center:
        logo_img_html = (
            f"<img src='data:image/png;base64,{LOGO_B64}' "
            f"style='height:180px; width:auto; object-fit:contain; display:block; margin-left:auto; margin-right:auto; margin-bottom:0.5rem; "
            f"filter:drop-shadow(0 0 20px rgba(90,235,86,0.35)); background:transparent;'/>"
            if LOGO_B64 else ""
        )
        st.markdown(f"""
        <div style="text-align:center; padding:0 1rem 0.75rem;">
          <div style="margin-bottom:0;">
            {logo_img_html}
          </div>
          <p style="font-family:'Manrope',sans-serif; font-size:0.95rem; color:#BCCBB4;
                    max-width:460px; margin:0 auto 2rem; line-height:1.65;">
            Analyzing suppliers, pricing signals, and logistics across 40+ markets
            with real-time risk assessment.
          </p>
        </div>
        """, unsafe_allow_html=True)

        # Intelligence panel
        st.markdown("""
        <div style="background:rgba(36,57,48,0.6); backdrop-filter:blur(20px);
                    border:1px solid rgba(90,235,86,0.1); border-radius:0.5rem;
                    padding:1.75rem 2rem; margin-bottom:1.5rem;
                    box-shadow:0 0 50px rgba(90,235,86,0.07);">
          <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:1.5rem; margin-bottom:1.5rem;">
            <div>
              <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.15em;
                        text-transform:uppercase; color:#879580; margin-bottom:0.2rem;">Suppliers Indexed</p>
              <p style="font-family:'Space Grotesk',sans-serif; font-size:1.7rem; font-weight:700;
                        color:#AEFFA0; margin:0; line-height:1.1;">89</p>
            </div>
            <div>
              <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.15em;
                        text-transform:uppercase; color:#879580; margin-bottom:0.2rem;">Countries Scanned</p>
              <p style="font-family:'Space Grotesk',sans-serif; font-size:1.7rem; font-weight:700;
                        color:#D0E8DA; margin:0; line-height:1.1;">21</p>
            </div>
            <div>
              <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.15em;
                        text-transform:uppercase; color:#879580; margin-bottom:0.2rem;">Forecast Horizon</p>
              <p style="font-family:'Space Grotesk',sans-serif; font-size:1.7rem; font-weight:700;
                        color:#AAF8FF; margin:0; line-height:1.1;">20<span style="font-size:0.9rem; font-weight:500;"> wks</span></p>
            </div>
            <div>
              <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.15em;
                        text-transform:uppercase; color:#879580; margin-bottom:0.2rem;">Service Level</p>
              <p style="font-family:'Space Grotesk',sans-serif; font-size:1.7rem; font-weight:700;
                        color:#AEFFA0; margin:0; line-height:1.1;">
                90<span style="font-size:0.9rem; font-weight:500;">%</span>
              </p>
            </div>
          </div>
          <div style="display:flex; align-items:center; justify-content:center; gap:0.5rem;">
            <span style="width:6px; height:6px; border-radius:50%; background:#5AEB56;
                         box-shadow:0 0 6px rgba(90,235,86,0.6);
                         animation:pulse 2s ease-in-out infinite;"></span>
            <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.28em;
                      text-transform:uppercase; color:rgba(90,235,86,0.55); margin:0;">
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
                  text-transform:uppercase; color:#879580; margin:0.25rem 0 0.75rem; text-align:center;">
          Try asking
        </p>
        """, unsafe_allow_html=True)

        _SUGGESTIONS = [
            ("Supplier allocation for transistors",   "Show supplier allocation for transistors"),
            ("LP optimization — country diversified", "Run LP optimization with country diversification"),
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
                 color:#D0E8DA; margin-bottom:0.25rem;">Session History</h2>
      <p style="font-family:'Manrope',sans-serif; font-size:0.85rem; color:#879580; margin:0;">
        Previously saved analyses — click any to review.
      </p>
    </div>
    """, unsafe_allow_html=True)

    history = st.session_state.chat_history
    if not history:
        st.markdown("""
        <div style="background:rgba(36,57,48,0.4); border:1px solid rgba(61,74,57,0.2);
                    border-radius:0.5rem; padding:2rem; text-align:center; color:#879580;
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
            <div style="background:rgba(36,57,48,0.45); border:1px solid rgba(61,74,57,0.2);
                        border-radius:0.375rem; padding:0.85rem 1.1rem; margin-bottom:0.5rem;">
              <p style="font-family:'Space Grotesk',sans-serif; font-size:0.9rem; font-weight:600;
                        color:#D0E8DA; margin:0 0 0.2rem;">{session['title']}</p>
              <p style="font-family:'Inter',sans-serif; font-size:0.7rem; color:#879580;
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
                    color:#D0E8DA; margin:0;">{session['title']}</p>
          <p style="font-family:'Inter',sans-serif; font-size:0.68rem; color:#879580;
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
                        + section_header("◎", "Visualizations", "#6CDD7F")
                        + "</div>",
                        unsafe_allow_html=True,
                    )
                    render_charts(chart_results)
                if msg.get("summary"):
                    st.markdown(msg["summary"])
        if msg.get("has_trace") and assistant_index < len(traces):
            show_trace_fn(traces[assistant_index])
            assistant_index += 1
