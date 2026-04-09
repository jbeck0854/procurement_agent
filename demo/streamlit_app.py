import asyncio
import base64
import logging
import uuid
from datetime import datetime
from pathlib import Path

import nest_asyncio
import streamlit as st
import streamlit.components.v1 as components

from langgraph.types import Command

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(message)s",
    datefmt="%H:%M:%S",
)

nest_asyncio.apply()

from graph.builder import build_graph

# ── Logo + avatars (loaded once at startup) ───────────────────────────────────
_logo_path        = Path(__file__).parent.parent / "ui_issues" / "logo_python.png"
_user_avatar_path = Path(__file__).parent.parent / "ui_issues" / "user.png"
_cpu_avatar_path  = Path(__file__).parent.parent / "ui_issues" / "cpu.png"
try:
    LOGO_B64 = base64.b64encode(_logo_path.read_bytes()).decode()
    from PIL import Image as _PILImage
    _favicon    = _PILImage.open(_logo_path)
    USER_AVATAR = _PILImage.open(_user_avatar_path)
    CPU_AVATAR  = _PILImage.open(_cpu_avatar_path)
except (FileNotFoundError, Exception):
    LOGO_B64    = ""
    _favicon    = "⬡"
    USER_AVATAR = "user"
    CPU_AVATAR  = "assistant"

st.set_page_config(
    page_title="Procurement Pilot",
    page_icon=_favicon,
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_graph():
    return build_graph()


graph = get_graph()

# ── Session state ─────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "traces" not in st.session_state:
    st.session_state.traces = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "waiting_for_approval" not in st.session_state:
    st.session_state.waiting_for_approval = False
if "pending_plan" not in st.session_state:
    st.session_state.pending_plan = None
if "plan_feedback" not in st.session_state:
    st.session_state.plan_feedback = ""
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []       # list of saved session dicts
if "current_view" not in st.session_state:
    st.session_state.current_view = "chat"   # "chat" | "history" | "history_detail"
if "viewing_session" not in st.session_state:
    st.session_state.viewing_session = None  # index into chat_history
if "suggested_query" not in st.session_state:
    st.session_state.suggested_query = ""


# ── CSS injection ─────────────────────────────────────────────────────────────
def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Manrope:wght@300;400;500;600;700;800&family=Inter:wght@400;500;600&display=swap');

    /* ── Base ── */
    html, body, .stApp {
        background-color: #03170F !important;
        font-family: 'Manrope', sans-serif !important;
        color: #D0E8DA !important;
    }
    /* Corner glow — bottom right */
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
    /* Keep stHeader in the DOM so its sidebar toggle button stays functional;
       just make it invisible (transparent bg, zero decoration). */
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

    /* ── Sidebar — always pinned open ── */
    /* Override Streamlit's collapse translateX so the panel never slides away. */
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
    /* Transparent wrappers so logo PNG shows on dark bg with no white box */
    .stMarkdown,
    [data-testid="stMarkdownContainer"],
    [data-testid="stMarkdownContainer"] > div,
    .element-container {
        background: transparent !important;
        background-color: transparent !important;
    }
    /* Sidebar button — override global style */
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
    /* Remove the extra top gap Streamlit adds before the first block element */
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
    /* User messages get a subtle green tint */
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
    /* Target the <p> Streamlit renders inside button elements */
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

    /* ── Text input — command line style ── */
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

    /* ── Inline result blocks (inside glass cards) ── */
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


# ── Persistent top nav (always rendered) ─────────────────────────────────────
def render_header():
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


# ── Sidebar ───────────────────────────────────────────────────────────────────
def render_sidebar():
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
        # Save current session before clearing, if it has messages
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
        st.session_state.current_view = "chat"
        st.session_state.viewing_session = None
        st.rerun()

    # ── Nav items ──
    # Inject CSS to make nav buttons look like list items (no button chrome)
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

    # Current Sourcing — active when in chat view
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

    # Session History — active when in history view
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

    # Static / decorative nav items
    for icon, label in [("◈", "Supplier Scorecard"), ("◷", "Risk Monitor")]:
        st.markdown(f"""
        <div style="display:flex; align-items:center; gap:0.7rem; padding:0.6rem 1.25rem;
                    margin-bottom:2px; font-family:'Manrope',sans-serif; font-size:0.85rem;
                    font-weight:500; color:#879580;">
          <span>{icon}</span><span>{label}</span>
        </div>""", unsafe_allow_html=True)

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


# ── Landing screen ────────────────────────────────────────────────────────────
def render_landing():
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

        # Suggestion chips — 2×2 grid
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


# ── Execution trace expander ──────────────────────────────────────────────────
def show_trace(trace):
    with st.expander("◈  Execution Trace"):
        timings = trace.get("timings") or {}
        if timings:
            st.markdown("""
            <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.15em;
               text-transform:uppercase; color:#879580; margin-bottom:0.5rem;">Performance</p>
            """, unsafe_allow_html=True)
            top_level = ["orchestrator", "data_agent", "risk_agent", "pipeline_agent",
                         "chart_agent", "lp_agent", "synthesizer"]
            active_agents = [n for n in top_level if timings.get(n) is not None]
            if active_agents:
                cols = st.columns(len(active_agents))
                for col, name in zip(cols, active_agents):
                    col.metric(name.replace("_", " ").title(), f"{timings[name]:.2f}s")
            total = sum(timings.get(k, 0) for k in top_level)
            st.caption(f"Total pipeline time: {total:.2f}s")
            sub_steps = {k: v for k, v in timings.items() if "." in k}
            if sub_steps:
                st.markdown("**Step breakdown:**\n" + "\n".join(
                    f"- {k}: {v:.3f}s" for k, v in sub_steps.items()
                ))
            st.divider()

        st.markdown("""
        <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.15em;
           text-transform:uppercase; color:#879580; margin-bottom:0.5rem;">Orchestrator</p>
        """, unsafe_allow_html=True)
        st.markdown(
            f"<span style='color:#AEFFA0; font-family:Manrope,sans-serif; font-weight:600;'>"
            f"{trace['intent']}</span>",
            unsafe_allow_html=True,
        )
        for i, task in enumerate(trace["tasks"]):
            st.markdown(f"""
            <div style="background:rgba(25,46,37,0.5); border:1px solid rgba(61,74,57,0.15);
                        border-radius:0.25rem; padding:0.7rem 1rem; margin:0.35rem 0;">
              <p style="font-family:'Inter',sans-serif; font-size:0.58rem; letter-spacing:0.12em;
                        text-transform:uppercase; color:#5AEB56; margin-bottom:0.3rem;">
                Task {i+1} — {task['agent']}
              </p>
              <p style="font-family:'Manrope',sans-serif; font-size:0.85rem; color:#D0E8DA; margin:0;">
                {task['objective']}
              </p>
            </div>""", unsafe_allow_html=True)

        if trace["tasks"]:
            routed = list({t["agent"] for t in trace["tasks"]})
            st.caption("Routed to: " + ", ".join(routed))

        pipeline_results = {k: v for k, v in trace["agent_results"].items()
                            if k in ("forecast_summary", "component_requirements", "procurement_status")}
        if pipeline_results:
            st.divider()
            st.caption("Pipeline Agent")
            for key, content in pipeline_results.items():
                st.caption(key.replace("_", " ").title())
                st.code(content)

        for agent_name, label in [("data_agent", "Data Agent"), ("risk_agent", "Risk Agent")]:
            raw = trace["agent_results"].get(agent_name)
            if raw:
                st.divider()
                st.caption(label)
                st.code(raw[:500] + ("..." if len(raw) > 500 else ""))

        lp_results = {k: v for k, v in trace["agent_results"].items() if k.startswith("lp_")}
        if lp_results:
            st.divider()
            st.caption("LP Optimization")
            for key, content in lp_results.items():
                product = key.replace("lp_", "").replace("_", " ").title()
                st.caption(f"Product: {product}")
                st.code(content)

        chart_results = trace.get("chart_results") or {}
        if chart_results:
            st.divider()
            st.caption("Charts")
            for chart_name, b64_img in chart_results.items():
                st.caption(chart_name)
                st.image(base64.b64decode(b64_img))

        st.divider()
        st.caption("Synthesizer — final response generated")


# ── Streaming execution ───────────────────────────────────────────────────────
AGENT_STEPS = [
    ("pipeline_agent", "Querying forecast & inventory data"),
    ("data_agent",     "Running exploratory SQL analysis"),
    ("risk_agent",     "Scanning geopolitical risk signals"),
    ("chart_agent",    "Generating visualizations & scoring"),
    ("lp_agent",       "Optimizing supplier allocation"),
    ("synthesizer",    "Synthesizing executive summary"),
]

_SECTION_STYLE = (
    "background:rgba(36,57,48,0.6); backdrop-filter:blur(20px);"
    "border:1px solid rgba(61,74,57,0.15); border-radius:0.5rem;"
    "padding:1.25rem 1.5rem; margin-bottom:0.875rem;"
    "box-shadow:0 0 40px rgba(90,235,86,0.06);"
)


def _section_header(icon, label, accent="#879580"):
    return (
        f"<div style='display:flex; align-items:center; gap:0.5rem; margin-bottom:0.875rem;'>"
        f"<span style='color:{accent}; font-size:0.9rem;'>{icon}</span>"
        f"<p style='font-family:Inter,sans-serif; font-size:0.58rem; letter-spacing:0.15em;"
        f"text-transform:uppercase; color:#879580; margin:0;'>{label}</p>"
        f"</div>"
    )


def _render_charts(charts: dict):
    """Render a dict of {chart_name: base64_png} in a 2-column grid."""
    items = list(charts.items())
    for i in range(0, len(items), 2):
        pair = items[i : i + 2]
        cols = st.columns(len(pair))
        for col, (chart_name, b64_img) in zip(cols, pair):
            with col:
                st.caption(chart_name.replace("_", " ").title())
                st.image(base64.b64decode(b64_img))


def stream_graph(command, config):
    placeholder = st.empty()
    final_state = {"agent_results": {}}

    def _render_streaming(placeholder):
        with placeholder.container():
            completed = set(final_state.get("_completed_agents") or [])
            active = final_state.get("_active_agent")

            # Progress feed
            rows = ""
            for agent_key, label in AGENT_STEPS:
                if agent_key in completed:
                    rows += (
                        f"<div style='display:flex; align-items:center; gap:0.75rem;"
                        f"padding:0.35rem 0; opacity:0.6;'>"
                        f"<span style='color:#5AEB56; flex-shrink:0;'>✓</span>"
                        f"<span style='font-family:Manrope,sans-serif; font-size:0.85rem;"
                        f"color:#D0E8DA;'>{label}</span></div>"
                    )
                elif agent_key == active:
                    rows += (
                        f"<div style='display:flex; align-items:center; gap:0.75rem;"
                        f"padding:0.35rem 0;'>"
                        f"<span style='color:#5AEB56; flex-shrink:0;'>◌</span>"
                        f"<span style='font-family:Manrope,sans-serif; font-size:0.85rem;"
                        f"color:#5AEB56; font-weight:700;'>{label}</span></div>"
                    )
                else:
                    rows += (
                        f"<div style='display:flex; align-items:center; gap:0.75rem;"
                        f"padding:0.35rem 0; opacity:0.55;'>"
                        f"<span style='color:#BCCBB4; flex-shrink:0;'>○</span>"
                        f"<span style='font-family:Manrope,sans-serif; font-size:0.85rem;"
                        f"color:#BCCBB4;'>{label}</span></div>"
                    )

            st.markdown(
                f"<div style='{_SECTION_STYLE}'>"
                + _section_header("⬡", "Active Engine Progress", "#5AEB56")
                + rows
                + "</div>",
                unsafe_allow_html=True,
            )

            # Pipeline results — inline content into glass card
            pipeline_results = final_state.get("pipeline_results") or {}
            if pipeline_results:
                _PIPELINE_LABELS = {
                    "forecast_summary": "Forecast Summary",
                    "component_requirements": "Component Requirements",
                    "procurement_status": "Procurement Status",
                }
                inner = "".join(
                    f"<p class='result-label'>{_PIPELINE_LABELS.get(k, k.replace('_',' ').title())}</p>"
                    f"<pre class='result-pre'>{v}</pre>"
                    for k, v in pipeline_results.items()
                )
                st.markdown(
                    f"<div style='{_SECTION_STYLE}'>"
                    + _section_header("✦", "Pipeline Results", "#AEFFA0")
                    + inner
                    + "</div>",
                    unsafe_allow_html=True,
                )

            # Data agent — inline into glass card
            if final_state.get("latest_data_agent"):
                inner = (
                    f"<div class='summary-body' style='font-size:0.88rem; color:#D0E8DA; line-height:1.65;'>"
                    f"{final_state['latest_data_agent']}</div>"
                )
                st.markdown(
                    f"<div style='{_SECTION_STYLE}'>"
                    + _section_header("◈", "Data Query", "#AAF8FF")
                    + inner
                    + "</div>",
                    unsafe_allow_html=True,
                )

            # Risk agent — inline into glass card
            if final_state.get("latest_risk_agent"):
                inner = (
                    f"<div class='summary-body' style='font-size:0.88rem; color:#D0E8DA; line-height:1.65;'>"
                    f"{final_state['latest_risk_agent']}</div>"
                )
                st.markdown(
                    f"<div style='{_SECTION_STYLE}'>"
                    + _section_header("⊕", "Geopolitical Risk Analysis", "#78F5FF")
                    + inner
                    + "</div>",
                    unsafe_allow_html=True,
                )

            # LP results — inline content into glass card
            lp_results = final_state.get("lp_results") or {}
            if lp_results:
                lp_style = (
                    "background:rgba(36,57,48,0.6); backdrop-filter:blur(20px);"
                    "border:1px solid rgba(61,74,57,0.15); border-left:3px solid #5AEB56;"
                    "border-radius:0.5rem; padding:1.25rem 1.5rem; margin-bottom:0.875rem;"
                )
                inner = "".join(
                    f"<p class='result-label'>Product: {k.replace('lp_','').replace('_',' ').title()}</p>"
                    f"<pre class='result-pre'>{v}</pre>"
                    for k, v in lp_results.items()
                )
                st.markdown(
                    f"<div style='{lp_style}'>"
                    + _section_header("◬", "LP Optimization Results", "#5AEB56")
                    + inner
                    + "</div>",
                    unsafe_allow_html=True,
                )

            # Charts — 2-column grid
            charts = final_state.get("chart_results") or {}
            if charts:
                st.markdown(
                    f"<div style='{_SECTION_STYLE}'>"
                    + _section_header("◎", "Visualizations", "#6CDD7F")
                    + "</div>",
                    unsafe_allow_html=True,
                )
                _render_charts(charts)

            # Summary — inline into glass card
            if final_state.get("final_response"):
                summary_style = (
                    "background:rgba(36,57,48,0.6); backdrop-filter:blur(20px);"
                    "border:1px solid rgba(90,235,86,0.18); border-radius:0.5rem;"
                    "padding:1.25rem 1.5rem; margin-bottom:0.875rem;"
                    "box-shadow:0 0 40px rgba(90,235,86,0.08);"
                )
                inner = (
                    f"<div class='summary-body'>{final_state['final_response']}</div>"
                )
                st.markdown(
                    f"<div style='{summary_style}'>"
                    + _section_header("✦", "Intelligence Summary", "#AEFFA0")
                    + inner
                    + "</div>",
                    unsafe_allow_html=True,
                )

    async def stream_results():
        agent_order = [s[0] for s in AGENT_STEPS]
        async for event in graph.astream(command, config=config):
            for node_name, node_output in event.items():
                if not isinstance(node_output, dict):
                    continue
                if node_name in agent_order:
                    final_state["_active_agent"] = node_name
                if "intent" in node_output:
                    final_state["intent"] = node_output["intent"]
                if "tasks" in node_output:
                    final_state["tasks"] = node_output["tasks"]
                if "agent_results" in node_output:
                    final_state.setdefault("agent_results", {}).update(
                        node_output["agent_results"] or {}
                    )
                if node_name == "pipeline_agent" and node_output.get("agent_results"):
                    items = {
                        k: v for k, v in node_output["agent_results"].items()
                        if k in ("forecast_summary", "component_requirements", "procurement_status")
                    }
                    if items:
                        final_state.setdefault("pipeline_results", {}).update(items)
                        final_state.setdefault("_completed_agents", []).append("pipeline_agent")
                        _render_streaming(placeholder)
                if node_name == "data_agent" and node_output.get("agent_results"):
                    data_text = node_output["agent_results"].get("data_agent")
                    if data_text:
                        final_state["latest_data_agent"] = data_text
                        final_state.setdefault("_completed_agents", []).append("data_agent")
                        _render_streaming(placeholder)
                if node_name == "risk_agent" and node_output.get("agent_results"):
                    risk_text = node_output["agent_results"].get("risk_agent")
                    if risk_text:
                        final_state["latest_risk_agent"] = risk_text
                        final_state.setdefault("_completed_agents", []).append("risk_agent")
                        _render_streaming(placeholder)
                if node_name == "lp_agent" and node_output.get("agent_results"):
                    lp_items = {
                        k: v for k, v in node_output["agent_results"].items()
                        if k.startswith("lp_")
                    }
                    if lp_items:
                        final_state.setdefault("lp_results", {}).update(lp_items)
                        final_state.setdefault("_completed_agents", []).append("lp_agent")
                        _render_streaming(placeholder)
                if node_name == "chart_agent" and node_output.get("chart_results"):
                    final_state.setdefault("chart_results", {}).update(
                        node_output["chart_results"]
                    )
                    final_state.setdefault("_completed_agents", []).append("chart_agent")
                    _render_streaming(placeholder)
                if node_name == "synthesizer" and "final_response" in node_output:
                    final_state["final_response"] = node_output["final_response"]
                    final_state["timings"] = node_output.get("timings", {})
                    final_state.setdefault("_completed_agents", []).append("synthesizer")
                    _render_streaming(placeholder)
                final_state[node_name] = node_output
        return final_state

    return asyncio.run(stream_results())


# ── Finalize execution ────────────────────────────────────────────────────────
def finalize_execution(final_state, fallback_plan=None):
    plan = fallback_plan or {}
    trace = {
        "intent": final_state.get("intent") or plan.get("intent", ""),
        "tasks": final_state.get("tasks") or plan.get("tasks", []),
        "agent_results": final_state.get("agent_results", {}),
        "chart_results": final_state.get("chart_results") or {},
        "timings": final_state.get("timings") or plan.get("timings", {}),
    }
    st.session_state.traces.append(trace)

    parts = []
    pipeline_items = {k: v for k, v in trace["agent_results"].items()
                      if k in ("forecast_summary", "component_requirements", "procurement_status")}
    if pipeline_items:
        pip_parts = [
            f"**{k.replace('_', ' ').title()}**\n\n```\n{v}\n```"
            for k, v in pipeline_items.items()
        ]
        parts.append("**Pipeline Results**\n\n" + "\n\n".join(pip_parts))
    data_result = trace["agent_results"].get("data_agent", "")
    if data_result:
        parts.append(data_result)
    risk_result = trace["agent_results"].get("risk_agent", "")
    if risk_result:
        parts.append("---\n\n**Geopolitical Risk Analysis**\n\n" + risk_result)
    lp_items = {k: v for k, v in trace["agent_results"].items() if k.startswith("lp_")}
    if lp_items:
        lp_parts = [
            f"**{k.replace('lp_', '').replace('_', ' ').title()}**\n\n```\n{v}\n```"
            for k, v in lp_items.items()
        ]
        parts.append("---\n\n**LP Optimization Results**\n\n" + "\n\n".join(lp_parts))

    final_response = final_state.get("final_response", "")
    summary_text = ("---\n\n**Intelligence Summary**\n\n" + final_response) if final_response else ""
    combined = "\n\n".join(parts)

    with st.chat_message("assistant", avatar=CPU_AVATAR):
        # Pipeline items — collapsible expanders so long outputs don't overwhelm the page
        if pipeline_items:
            _PIPELINE_EXPAND_DEFAULT = {
                "forecast_summary": True,
                "component_requirements": False,
                "procurement_status": False,
            }
            st.markdown(
                "<p style='font-family:Inter,sans-serif; font-size:0.6rem; letter-spacing:0.12em;"
                "text-transform:uppercase; color:#879580; margin:0 0 0.4rem;'>Pipeline Results</p>",
                unsafe_allow_html=True,
            )
            for key, content in pipeline_items.items():
                label = key.replace("_", " ").title()
                expanded = _PIPELINE_EXPAND_DEFAULT.get(key, False)
                with st.expander(label, expanded=expanded):
                    st.code(content, language=None)
        if data_result:
            st.markdown(data_result)
        if risk_result:
            st.markdown("---\n\n**Geopolitical Risk Analysis**\n\n" + risk_result)
        if lp_items:
            st.markdown("---")
            st.markdown(
                "<p style='font-family:Inter,sans-serif; font-size:0.6rem; letter-spacing:0.12em;"
                "text-transform:uppercase; color:#879580; margin:0 0 0.4rem;'>LP Optimization Results</p>",
                unsafe_allow_html=True,
            )
            for key, content in lp_items.items():
                product = key.replace("lp_", "").replace("_", " ").title()
                with st.expander(f"Product: {product}", expanded=True):
                    st.code(content, language=None)
        chart_results = trace.get("chart_results") or {}
        if chart_results:
            st.markdown(
                f"<div style='margin:0.75rem 0 0.5rem;'>"
                + _section_header("◎", "Visualizations", "#6CDD7F")
                + "</div>",
                unsafe_allow_html=True,
            )
            _render_charts(chart_results)
        if summary_text:
            st.markdown(summary_text)

    st.session_state.messages.append({
        "role": "assistant",
        "content": combined,
        "summary": summary_text,
        "has_trace": True,
    })
    show_trace(trace)

    # Export button
    export_content = f"# Procurement Intelligence Report\n\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    if trace.get("intent"):
        export_content += f"**Query Intent:** {trace['intent']}\n\n---\n\n"
    if combined:
        export_content += combined + "\n\n"
    if final_response:
        export_content += "## Intelligence Summary\n\n" + final_response
    if export_content.strip():
        st.download_button(
            label="↓  Export Report",
            data=export_content,
            file_name=f"procurement_report_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
            mime="text/markdown",
            key=f"export_{len(st.session_state.traces)}",
        )

    return combined


# ── Plan extraction ───────────────────────────────────────────────────────────
def extract_plan(state):
    interrupts = []
    for task in state.tasks or []:
        interrupts.extend(task.interrupts or [])
    return interrupts[0].value if interrupts else None


# ── Approval panel ────────────────────────────────────────────────────────────
def render_pending_plan():
    plan = st.session_state.pending_plan or {}
    tasks = plan.get("tasks", [])

    # Header card
    question_html = ""
    if plan.get("question"):
        question_html = (
            "<div style='background:rgba(170,248,255,0.05); border:1px solid rgba(170,248,255,0.15);"
            "border-radius:0.25rem; padding:0.75rem 1rem; margin-bottom:1.25rem;'>"
            f"<p style='font-family:Manrope,sans-serif; font-size:0.875rem; color:#AAF8FF; margin:0;'>"
            f"{plan['question']}</p></div>"
        )

    st.markdown(
        f"<div style='{_SECTION_STYLE}'>"
        "<div style='display:flex; align-items:center; gap:0.55rem; margin-bottom:1.25rem;'>"
        "<span style='font-size:1rem; color:#5AEB56;'>✦</span>"
        "<h2 style='font-family:Space Grotesk,sans-serif; font-size:1.2rem; font-weight:700;"
        "letter-spacing:-0.02em; color:#D0E8DA; margin:0;'>Intelligence Plan Ready</h2>"
        "</div>"
        "<div style='background:rgba(90,235,86,0.06); border:1px solid rgba(90,235,86,0.14);"
        "border-radius:0.25rem; padding:0.75rem 1rem; margin-bottom:1.25rem;'>"
        "<p style='font-family:Inter,sans-serif; font-size:0.58rem; letter-spacing:0.15em;"
        "text-transform:uppercase; color:#879580; margin-bottom:0.3rem;'>Intent</p>"
        f"<p style='font-family:Manrope,sans-serif; font-size:0.9rem; color:#AEFFA0; margin:0;"
        f"font-weight:600;'>{plan.get('intent', '')}</p>"
        "</div>"
        + question_html
        + f"<p style='font-family:Inter,sans-serif; font-size:0.58rem; letter-spacing:0.15em;"
        f"text-transform:uppercase; color:#879580; margin-bottom:0.75rem;'>"
        f"Work Orders — {len(tasks)} task{'s' if len(tasks) != 1 else ''}</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    # Task cards
    agent_accent = {
        "pipeline_agent": "#AEFFA0",
        "data_agent":     "#AAF8FF",
        "risk_agent":     "#78F5FF",
        "chart_agent":    "#6CDD7F",
        "lp_agent":       "#AEFFA0",
    }
    for i, task in enumerate(tasks):
        agent = task.get("agent", "")
        accent = agent_accent.get(agent, "#BCCBB4")
        ctx_html = (
            f"<p style='font-family:Manrope,sans-serif; font-size:0.8rem; color:#879580; margin:0.25rem 0 0;'>"
            f"{task.get('context', '')}</p>"
            if task.get("context") else ""
        )
        instr_html = (
            f"<p style='font-family:Inter,sans-serif; font-size:0.75rem; color:#BCCBB4; margin:0.2rem 0 0;'>"
            f"{task.get('instructions', '')}</p>"
            if task.get("instructions") else ""
        )
        st.markdown(
            "<div style='background:rgba(25,46,37,0.7); border:1px solid rgba(61,74,57,0.2);"
            "border-radius:0.25rem; padding:0.875rem 1.25rem; margin-bottom:0.4rem;'>"
            "<div style='display:flex; align-items:center; gap:0.5rem; margin-bottom:0.4rem;'>"
            f"<span style='font-family:Inter,sans-serif; font-size:0.55rem; letter-spacing:0.12em;"
            f"text-transform:uppercase; color:#879580;'>Task {i+1}</span>"
            f"<span style='font-family:Inter,sans-serif; font-size:0.55rem; font-weight:600;"
            f"letter-spacing:0.1em; text-transform:uppercase; color:{accent};"
            f"background:rgba(90,235,86,0.07); border:1px solid rgba(90,235,86,0.14);"
            f"padding:0.1rem 0.45rem; border-radius:0.125rem;'>{agent}</span>"
            "</div>"
            f"<p style='font-family:Manrope,sans-serif; font-size:0.875rem; font-weight:600;"
            f"color:#D0E8DA; margin:0;'>{task.get('objective', '')}</p>"
            + ctx_html + instr_html
            + "</div>",
            unsafe_allow_html=True,
        )

    # Input + button
    st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.text_input(
            "Modify the plan (optional)",
            key="plan_feedback",
            placeholder="Leave blank to approve as-is...",
        )
        if st.button("Approve & Execute", key="approve_plan", use_container_width=True):
            with st.spinner("Executing approved plan..."):
                feedback = st.session_state.plan_feedback.strip() or "ok"
                config = {"configurable": {"thread_id": st.session_state.thread_id}}
                final_state = stream_graph(Command(resume=feedback), config=config)
            state = asyncio.run(graph.aget_state(config=config))
            next_plan = extract_plan(state)
            if state.next and next_plan:
                st.session_state.pending_plan = next_plan
                st.session_state.messages.append(
                    {"role": "assistant", "content": "Plan updated. Review the new work orders below."}
                )
                st.rerun()
            else:
                finalize_execution(final_state, fallback_plan=plan)
                st.session_state.waiting_for_approval = False
                st.session_state.pending_plan = None
                st.rerun()


# ── Session history views ─────────────────────────────────────────────────────
def render_history_list():
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
        idx = len(history) - 1 - i   # real index in chat_history list
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


def render_history_detail():
    idx = st.session_state.viewing_session
    session = st.session_state.chat_history[idx]
    ts = session["timestamp"].strftime("%b %d, %Y  %H:%M")

    # Back button + title
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

    # Replay the messages from the saved session
    traces = session.get("traces", [])
    assistant_index = 0
    for msg in session["messages"]:
        with st.chat_message(msg["role"], avatar=USER_AVATAR if msg["role"] == "user" else CPU_AVATAR):
            if msg.get("content"):
                st.markdown(msg["content"])
            if msg.get("has_trace") and assistant_index < len(traces):
                chart_results = traces[assistant_index].get("chart_results") or {}
                if chart_results:
                    st.markdown(
                        "<div style='margin:0.75rem 0 0.35rem;'>"
                        + _section_header("◎", "Visualizations", "#6CDD7F")
                        + "</div>",
                        unsafe_allow_html=True,
                    )
                    _render_charts(chart_results)
                if msg.get("summary"):
                    st.markdown(msg["summary"])
        if msg.get("has_trace") and assistant_index < len(traces):
            show_trace(traces[assistant_index])
            assistant_index += 1


# ═════════════════════════════════════════════════════════════════════════════
# Main app
# ═════════════════════════════════════════════════════════════════════════════
inject_css()
render_header()

with st.sidebar:
    render_sidebar()

# ── Route on current_view ─────────────────────────────────────────────────────
if st.session_state.current_view == "history":
    render_history_list()
elif st.session_state.current_view == "history_detail":
    render_history_detail()
else:
    # ── current_view == "chat" ────────────────────────────────────────────────
    # Replay current session messages
    assistant_index = 0
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar=USER_AVATAR if msg["role"] == "user" else CPU_AVATAR):
            if msg.get("content"):
                st.markdown(msg["content"])
            if msg.get("has_trace") and assistant_index < len(st.session_state.traces):
                chart_results = st.session_state.traces[assistant_index].get("chart_results") or {}
                if chart_results:
                    st.markdown(
                        "<div style='margin:0.75rem 0 0.35rem;'>"
                        + _section_header("◎", "Visualizations", "#6CDD7F")
                        + "</div>",
                        unsafe_allow_html=True,
                    )
                    _render_charts(chart_results)
                if msg.get("summary"):
                    st.markdown(msg["summary"])
        if msg.get("has_trace") and assistant_index < len(st.session_state.traces):
            show_trace(st.session_state.traces[assistant_index])
            assistant_index += 1

    # ── Landing / approval / chat input ──────────────────────────────────────
    if not st.session_state.messages:
        render_landing()

    if st.session_state.waiting_for_approval and st.session_state.pending_plan:
        render_pending_plan()
    elif not st.session_state.waiting_for_approval:
        # Check for a suggestion chip click first, then fall back to typed input
        _suggested = st.session_state.pop("suggested_query", "") or ""
        prompt = _suggested or st.chat_input("Ask a sourcing query...")
        if prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user", avatar=USER_AVATAR):
                st.write(prompt)
            with st.spinner("Initializing procurement matrix..."):
                thread_id = str(uuid.uuid4())
                st.session_state.thread_id = thread_id
                config = {"configurable": {"thread_id": thread_id}}
                result = asyncio.run(
                    graph.ainvoke({"messages": [("user", prompt)]}, config=config)
                )
                state = asyncio.run(graph.aget_state(config=config))
            plan = extract_plan(state)
            if state.next and plan:
                st.session_state.waiting_for_approval = True
                st.session_state.pending_plan = plan
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": "Intelligence plan ready. Review the work orders below and approve when ready.",
                })
                st.rerun()
