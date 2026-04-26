import base64
import re


def _extract_facility_id(text: str) -> str | None:
    """Extract FACILITY_N from free text (e.g. 'Facility 2' → 'FACILITY_2')."""
    m = re.search(r'facilit(?:y|_)?[\s_]?(\d)', text.lower())
    return f"FACILITY_{m.group(1)}" if m else None


def _format_facility_label(facility_id: str) -> str:
    """Convert DB-format 'FACILITY_1' to business-facing 'Facility 1'."""
    m = re.match(r'FACILITY_(\d+)', facility_id, re.IGNORECASE)
    return f"Facility {m.group(1)}" if m else facility_id


def _fig_to_b64(fig) -> str:
    """Serialize a matplotlib Figure to base64-encoded PNG string.

    Used by fast-path drill-down handlers to persist charts across st.rerun().
    The b64 string is stored in the message dict under 'chart_b64' and decoded
    by the replay loop with st.image(base64.b64decode(msg['chart_b64'])).
    """
    import io
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def _inject_scroll_to_bottom() -> None:
    """
    Inject a zero-height JS component that scrolls the Streamlit main pane
    to the bottom (newest content).  Safe to call on every render — only fired
    when message count has increased since the last scroll, so widget
    interactions (filter multiselects, expander toggles) never trigger a jump.
    """
    import streamlit.components.v1 as _stcomps
    _stcomps.html(
        """
        <script>
        (function() {
            var doc = window.parent.document;
            var el = doc.querySelector('section[data-testid="stMain"]')
                  || doc.querySelector('.main');
            if (el) { el.scrollTop = el.scrollHeight; }
        })();
        </script>
        """,
        height=0,
        scrolling=False,
    )


def _inject_scroll_to_anchor(anchor_id: str) -> None:
    """
    Inject a zero-height JS component that scrolls the Streamlit main pane
    to a named anchor element (identified by id).  Used for section-level
    anchoring (e.g. Final Executive Summary top, LP result top).
    """
    import streamlit.components.v1 as _stcomps
    _stcomps.html(
        f"""
        <script>
        (function() {{
            var doc = window.parent.document;
            var anchor = doc.getElementById('{anchor_id}');
            if (anchor) {{
                var mainEl = doc.querySelector('section[data-testid="stMain"]')
                           || doc.querySelector('.main');
                if (mainEl) {{
                    var anchorTop = anchor.getBoundingClientRect().top;
                    var mainTop   = mainEl.getBoundingClientRect().top;
                    mainEl.scrollTop += anchorTop - mainTop - 20;
                }}
            }}
        }})();
        </script>
        """,
        height=0,
        scrolling=False,
    )
