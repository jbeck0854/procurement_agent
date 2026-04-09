# UI Changes — Streamlit App

All changes are in `demo/streamlit_app.py`.

---

## 1. Fixed Broken Glass Cards

**Problem:** Section containers (`_render_streaming()`) closed their `<div>` immediately after the header label. Agent output (code blocks, markdown) rendered outside the styled glass card as bare Streamlit elements.

**Fix:** Section content is now built as HTML and included inside the glass `<div>` before it closes:
- Pipeline results and LP results use `<pre class='result-pre'>` — dark background, green monospace text, scrollable with `max-height: 220px`
- Data agent and risk agent text use `<div class='summary-body'>` — prose styling
- Intelligence summary uses `<div class='summary-body'>` inside a green-bordered glass card

Two CSS classes added to `inject_css()`:
- `.result-label` — uppercase Inter label above each block
- `.result-pre` — styled scrollable code block

---

## 2. Charts 2-Column Grid

**Problem:** Charts stacked one per row with a plain `st.caption()` label — long scroll with multiple charts.

**Fix:** New helper `_render_charts(charts: dict)` renders charts in pairs using `st.columns(2)`. Applied in all 4 rendering locations:
- `_render_streaming()` (live streaming view)
- `finalize_execution()` (post-execution chat message)
- Live chat session replay (main loop)
- `render_history_detail()` (session history replay)

---

## 3. Landing Page Query Suggestions

**Problem:** Landing page showed metrics but gave no indication of what to type.

**Fix:** Two clickable suggestion chips in a single row added below the metrics panel in `render_landing()`:
- "Supplier allocation for transistors"
- "LP optimization — country diversified"

Clicking a chip sets `st.session_state.suggested_query` and reruns. The main chat input block checks for `suggested_query` before falling back to `st.chat_input()`.

CSS class `.suggestion-row` styles the chips as rectangular ghost buttons (dark background, green border on hover) with fixed equal height.

---

## 4. Better Pipeline Data Display

**Problem:** Forecast summary, component requirements, and procurement status rendered as raw unstyled `st.code()` blocks in the finalized chat message — long, overwhelming output.

**Fix:** In `finalize_execution()`, pipeline results are now wrapped in `st.expander()`:
- `Forecast Summary` — expanded by default
- `Component Requirements` — collapsed by default
- `Procurement Status` — collapsed by default

LP results per product are also shown in expanders (expanded by default).

Note: During live streaming (`_render_streaming()`), pipeline content is still inlined into the glass card HTML with scrollable `<pre>` blocks (see Change 1).

---

## 5. Execution Trace in Session History

**Problem:** `render_history_detail()` showed charts and the intelligence summary when replaying a saved session, but the execution trace expander was missing.

**Fix:** `show_trace()` is now called in `render_history_detail()` after each assistant message that has a trace, mirroring the live chat view.

---

## 6. Export Intelligence Summary

**Problem:** No way to save the output of a query.

**Fix:** A `↓ Export Report` download button is rendered in `finalize_execution()` after `show_trace()`. The exported file is a Markdown document containing:
- Generation timestamp
- Parsed query intent
- All agent results (pipeline, data, risk, LP)
- Intelligence summary

File is named `procurement_report_YYYYMMDD_HHMM.md`.

---

## 7. Favicon

**Fix:** Logo PNG (`ui_issues/logo_python.png`) loaded as a PIL Image and passed to `st.set_page_config(page_icon=...)`. Falls back to `⬡` emoji if the file is missing.

---

## 8. Landing Page Logo Size & Gap

**Fix:** Logo height reduced from 360px → 180px so the full landing page fits in one viewport without scrolling. Negative `margin-bottom` hack removed. Block-container `padding-top` reduced to `3.75rem` to just clear the fixed header. CSS rules added to zero out Streamlit's internal column top margin/padding.

---

## 9. Suggestion Chips Layout

**Fix:** Reduced from a 2×2 grid to a single row of 2 chips. Chips styled with fixed `height: 3rem`, `white-space: nowrap`, and `text-overflow: ellipsis` so they are always equal size regardless of label length.

---

## 10. Sidebar — Branding & Spacing

- "Logic Interface" label replaced with "Procurement Pilot"
- Sidebar logo height increased from 40px → 64px
- Spacer divs between the header, New Analysis button, and nav items removed

---

## 11. Custom Chat Avatars

**Problem:** Streamlit's default generic user/bot icons used in all chat messages.

**Fix:** `ui_issues/user.png` (person silhouette) and `ui_issues/cpu.png` (processor icon) loaded as PIL Images at startup and passed as `avatar=` to all `st.chat_message()` calls:
- User messages → `user.png`
- Assistant messages → `cpu.png`

Applied in all four locations: new message submission, `finalize_execution()`, live chat replay, and `render_history_detail()`. Falls back to Streamlit's default role strings if files are not found.
