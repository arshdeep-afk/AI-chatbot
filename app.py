"""
app.py  —  FY26 AI Data Analyst (Streamlit)

Run with:
    streamlit run app.py
"""

import os
import sys
import traceback

import pandas as pd
import streamlit as st

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.data_loader import (
    ACTUAL_MONTHS,
    get_long,
    get_long_with_agg,
    get_schema_info,
    get_schema_info_from_dfs,
    load_fy26_wide_from_bytes,
    melt_to_long,
)
from backend.query_engine import execute_query
from backend.visualization_engine import auto_charts, ALL_CHART_TYPES, COLOR_THEMES
import streamlit.components.v1 as _components
from ai.query_parser import parse_query, generate_data_answer

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FY26 AI Data Analyst",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
.header-box {
    background: linear-gradient(135deg, #1a3a6c 0%, #2e6da4 100%);
    color: white;
    padding: 1.4rem 2rem;
    border-radius: 12px;
    margin-bottom: 1rem;
}
.insight-box {
    background: #eaf4fb;
    border-left: 4px solid #2e6da4;
    border-radius: 6px;
    padding: .75rem 1rem;
    margin-top: .5rem;
    font-size: .94rem;
    line-height: 1.5;
    color: #111111 !important;
}
.insight-box * {
    color: #111111 !important;
}
.stChatMessage { padding: .3rem 0; }
.chart-toast {
    background: #f0f7ff;
    border: 1px solid #c8e0f4;
    border-left: 3px solid #2e6da4;
    border-radius: 6px;
    padding: .4rem .8rem;
    margin: .3rem 0 .4rem;
    font-size: .9rem;
    color: #1a3a6c;
}
</style>
""",
    unsafe_allow_html=True,
)

# ── Session state ──────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "example_q" not in st.session_state:
    st.session_state.example_q = None
if "uploaded_bytes" not in st.session_state:
    st.session_state.uploaded_bytes = None
if "uploaded_name" not in st.session_state:
    st.session_state.uploaded_name = None

# ── Cached data loader ─────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_all(file_bytes=None):
    if file_bytes is not None:
        df_wide = load_fy26_wide_from_bytes(file_bytes)
        df      = melt_to_long(df_wide)
        df_all  = melt_to_long(df_wide, include_aggregates=True)
        schema  = get_schema_info_from_dfs(df, df_all)
    else:
        df      = get_long()
        df_all  = get_long_with_agg()
        schema  = get_schema_info()
    return df, df_all, schema


# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(
    """
<div class="header-box">
  <h1 style="margin:0;font-size:1.75rem">📊 FY26 AI Data Analyst</h1>
  <p style="margin:.25rem 0 0;opacity:.87">
    Ask questions about FY26 sales in plain English — get charts, tables & insights
  </p>
</div>
""",
    unsafe_allow_html=True,
)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📂 Data File")
    uploaded_file = st.file_uploader(
        "Upload your Excel dashboard",
        type=["xlsx", "xls"],
        help="Must contain a sheet named 'FY26' in the standard dashboard format",
    )
    if uploaded_file is not None:
        new_bytes = uploaded_file.read()
        if new_bytes != st.session_state.uploaded_bytes:
            st.session_state.uploaded_bytes = new_bytes
            st.session_state.uploaded_name  = uploaded_file.name
            st.session_state.messages       = []
            st.rerun()
    if st.session_state.uploaded_name:
        st.caption(f"✅ {st.session_state.uploaded_name}")

    st.markdown("---")
    st.markdown("### ⚙️ API Keys")
    if os.getenv("ANTHROPIC_API_KEY"):
        st.success("Anthropic key configured", icon="🔑")
    else:
        api_key_input = st.text_input(
            "Anthropic API Key",
            type="password",
            help="Get yours at console.anthropic.com",
        )
        if api_key_input:
            os.environ["ANTHROPIC_API_KEY"] = api_key_input

    if os.getenv("TAVILY_API_KEY"):
        st.success("Web search enabled", icon="🌐")
    else:
        tavily_input = st.text_input(
            "Tavily API Key *(optional)*",
            type="password",
            help="Enables live web search for competitor data. Free tier at tavily.com",
        )
        if tavily_input:
            os.environ["TAVILY_API_KEY"] = tavily_input

    st.markdown("---")
    st.markdown("### 💡 Example Questions")

    EXAMPLES = [
        "Which country had the highest revenue in Feb-26?",
        "Compare all sales directors by YTD value",
        "Show monthly revenue trend for Egypt",
        "Top 10 countries by total FY26 units",
        "Which category has the best gross margin in Feb-26?",
        "Which sub-category has the highest ASP in Feb-26?",
        "Show DCB revenue by country for Feb-26",
        "How does Sandeep's revenue compare month by month?",
        "What percentage of FY26 revenue comes from each category?",
        "Which countries had zero revenue in Feb-26?",
    ]

    for q in EXAMPLES:
        if st.button(q, key=f"ex_{abs(hash(q))}", use_container_width=True):
            st.session_state.example_q = q
            st.rerun()

    st.markdown("---")
    st.markdown("### 📊 Chart Preferences")

    selected_theme = st.selectbox(
        "Color theme",
        options=list(COLOR_THEMES.keys()),
        index=0,
        help="Pick a color palette for all charts",
    )
    st.caption("Click the chart type tabs on any response to switch graph.")

    st.markdown("---")
    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ── Load data ──────────────────────────────────────────────────────────────────
_uploaded = st.session_state.uploaded_bytes

if not _uploaded:
    st.info("📂 Upload your Excel dashboard file in the sidebar to get started.")
    st.stop()

try:
    with st.spinner("Loading dataset…"):
        df, df_all, schema_info = load_all(_uploaded)
except Exception as exc:
    st.error(f"❌ Failed to load Excel data: {exc}")
    st.stop()

# ── KPI strip ──────────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)

with k1:
    ytd_mask = df_all["Month"] == "YTD"
    ytd_rev = df_all.loc[ytd_mask, "Value"].sum() if ytd_mask.any() else df["Value"].sum()
    st.metric("YTD Revenue", f"€{ytd_rev:,.0f}K")

with k2:
    ytd_units = df_all.loc[ytd_mask, "Units"].sum() if ytd_mask.any() else df["Units"].sum()
    st.metric("YTD Units", f"{int(ytd_units):,}")

with k3:
    st.metric("Active Countries", df["Country"].nunique())

with k4:
    avail_months = [m for m in ACTUAL_MONTHS if m in df["Month"].values]
    latest_month = avail_months[-1] if avail_months else None
    if latest_month:
        latest_rev = df.loc[df["Month"] == latest_month, "Value"].sum()
        st.metric(f"{latest_month} Revenue", f"€{latest_rev:,.0f}K")
    else:
        st.metric("Latest Revenue", "N/A")

st.markdown("---")

# ── Graph keyword detection ────────────────────────────────────────────────────
_GRAPH_PHRASES = [
    "graph", "chart", "plot", "visualize", "visualise", "visualisation",
    "visualization", "diagram", "histogram", "treemap", "trend",
]

# (label, chart_types list passed to auto_charts, or None = ALL_CHART_TYPES)
_CHART_QUICK_OPTIONS = [
    ("📊 Bar",     ["Bar"]),
    ("📈 Line",    ["Line Trend"]),
    ("🥧 Pie",     ["Pie / Donut"]),
    ("📉 Grouped", ["Grouped Bar"]),
    ("🌲 Treemap", ["Treemap"]),
    ("✨ All",     None),
]

def _wants_graph(question: str) -> bool:
    """Return True if the question explicitly requests a chart/graph."""
    q = question.lower()
    return any(p in q for p in _GRAPH_PHRASES)


# ── Chart tab labels ───────────────────────────────────────────────────────────
_CHART_TAB_LABELS = {
    "bar":         "Bar",
    "hbar":        "H. Bar",
    "pie":         "Pie",
    "line":        "Line",
    "grouped_bar": "Grouped",
    "treemap":     "Treemap",
}


def render_charts(result, x_col, y_col, title, theme, chart_types=None):
    """Generate chart types and display them in clickable tabs."""
    charts = auto_charts(
        result,
        x_col=x_col,
        y_col=y_col,
        title=title,
        chart_types=chart_types or ALL_CHART_TYPES,
        color_theme=theme,
    )
    if not charts:
        return
    tab_labels = [_CHART_TAB_LABELS.get(ct, ct.title()) for ct, _ in charts]
    tabs = st.tabs(tab_labels)
    for tab, (_, fig) in zip(tabs, charts):
        with tab:
            st.plotly_chart(fig, use_container_width=True)


# ── Chat history display ───────────────────────────────────────────────────────
st.markdown("### 💬 Ask About Your Data")

for _i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            # Web sources
            if msg.get("web_sources"):
                src_links = " · ".join(
                    f"[{s['title'][:60]}]({s['url']})" for s in msg["web_sources"]
                )
                st.markdown(f"<small>🌐 **Sources:** {src_links}</small>",
                            unsafe_allow_html=True)

            # Chart toast / show-hide — only when chart data is available
            if msg.get("table_json") and msg.get("x_col"):
                _type_key = f"chart_type_{_i}"
                if _type_key not in st.session_state:
                    # Old messages default to shown (all types); new follow wants_graph
                    st.session_state[_type_key] = (
                        ALL_CHART_TYPES if msg.get("wants_graph", True) else None
                    )

                # Rebuild comparison DataFrame if competitor_bars were saved
                _hist_x     = msg["x_col"]
                _hist_title = msg.get("chart_title", "")
                _hist_result = None
                try:
                    _hist_result = pd.read_json(msg["table_json"], orient="split")
                except Exception:
                    pass

                _comp_bars = msg.get("competitor_bars") or []
                if _comp_bars and _hist_result is not None and msg.get("y_col"):
                    try:
                        _y = msg["y_col"]
                        _our_val = float(_hist_result[_y].sum()) if _y in _hist_result.columns else None
                        if _our_val is not None:
                            _comp_rows = [{"Entity": "Our Company (FY26 YTD)", _y: _our_val}]
                            _comp_rows += [{"Entity": b["label"], _y: b["value"]} for b in _comp_bars]
                            _hist_result = pd.DataFrame(_comp_rows)
                            _hist_x      = "Entity"
                            _hist_title  = _hist_title + " \u2014 Comparison"
                    except Exception:
                        pass

                if st.session_state[_type_key] is None:
                    # ── Toast prompt ──────────────────────────────────────────
                    st.markdown(
                        '<div class="chart-toast">📊 <b>Would you like to visualise this data?</b></div>',
                        unsafe_allow_html=True,
                    )
                    _cols = st.columns(len(_CHART_QUICK_OPTIONS))
                    for _col, (_label, _types) in zip(_cols, _CHART_QUICK_OPTIONS):
                        if _col.button(_label, key=f"chartopt_{_label}_{_i}"):
                            st.session_state[_type_key] = _types or ALL_CHART_TYPES
                            st.rerun()
                else:
                    # ── Charts shown ──────────────────────────────────────────
                    _hcol, _ = st.columns([1.4, 8.6])
                    if _hcol.button("🙈 Hide", key=f"hide_chart_{_i}"):
                        st.session_state[_type_key] = None
                        st.rerun()
                    if _hist_result is not None:
                        try:
                            render_charts(_hist_result, _hist_x, msg["y_col"],
                                          _hist_title, selected_theme,
                                          chart_types=st.session_state[_type_key])
                        except Exception:
                            pass

            # Re-render table
            if msg.get("table_json"):
                try:
                    tbl = pd.read_json(msg["table_json"], orient="split")
                    with st.expander("📋 Data Table"):
                        st.dataframe(tbl.head(50).reset_index(drop=True), use_container_width=True)
                except Exception:
                    pass
            # Re-render insight
            if msg.get("insight"):
                st.markdown(
                    f'<div class="insight-box">💡 <b>Insight:</b> {msg["insight"]}</div>',
                    unsafe_allow_html=True,
                )
            # Re-render code (only for real data queries)
            if msg.get("code") and msg.get("x_col"):
                with st.expander("🔍 Query Code"):
                    st.code(msg["code"], language="python")


# ── Core processing function ───────────────────────────────────────────────────
def process(question: str):
    if not question.strip():
        return

    # Display user turn
    with st.chat_message("user"):
        st.markdown(question)
    st.session_state.messages.append({"role": "user", "content": question})
    # Index the assistant reply will occupy — needed for chart-state keys
    _new_msg_idx = len(st.session_state.messages)

    with st.chat_message("assistant"):
        if not os.getenv("ANTHROPIC_API_KEY"):
            st.error("Please enter your Anthropic API key in the sidebar.")
            return

        with st.spinner("Analysing with Claude Opus 4.6…"):
            try:
                # Build a short conversation history for context
                history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages[:-1][-6:]
                ]

                # ── Step 1: AI interprets the question ────────────────────────
                parsed           = parse_query(question, schema_info, history)
                answer           = parsed.get("answer", "")
                code             = parsed.get("query_code", "")
                x_col            = parsed.get("x_col")
                y_col            = parsed.get("y_col")
                chart_title      = parsed.get("chart_title", question[:60])
                insight          = parsed.get("insight", "")
                competitor_bars  = parsed.get("competitor_bars") or []
                web_sources      = parsed.get("_web_sources") or []

                # ── Step 2: Execute generated pandas code ─────────────────────
                result, err = None, ""
                if code:
                    result, err = execute_query(code, df, df_all)

                # ── Step 2b: Enrich answer with actual data (Haiku, fast) ──────
                if result is not None and x_col and not err:
                    answer, insight = generate_data_answer(
                        question, result, answer, insight
                    )

                # ── Step 3: Display text answer ───────────────────────────────
                st.markdown(answer)
                if err:
                    st.warning(f"ℹ️ Query note: {err}")

                # ── Step 3b: Web sources ──────────────────────────────────────
                if web_sources:
                    src_links = " · ".join(
                        f"[{s['title'][:60]}]({s['url']})" for s in web_sources
                    )
                    st.markdown(f"<small>🌐 **Sources:** {src_links}</small>",
                                unsafe_allow_html=True)

                # ── Step 4: Charts (tabbed) ───────────────────────────────────
                wants_graph = _wants_graph(question)
                has_charts  = False
                _ck = f"chart_type_{_new_msg_idx}"
                # Prime state on first render
                if _ck not in st.session_state:
                    st.session_state[_ck] = ALL_CHART_TYPES if wants_graph else None

                if result is not None and x_col:
                    has_charts = True

                    # Build comparison DataFrame when Claude returns competitor_bars
                    chart_result = result
                    chart_x      = x_col
                    chart_title_ = chart_title
                    if competitor_bars and y_col:
                        try:
                            if isinstance(result, pd.Series):
                                our_val = float(result.sum())
                            elif isinstance(result, pd.DataFrame) and y_col in result.columns:
                                our_val = float(result[y_col].sum())
                            else:
                                our_val = None
                            if our_val is not None:
                                comp_rows = [{"Entity": "Our Company (FY26 YTD)", y_col: our_val}]
                                comp_rows += [{"Entity": b["label"], y_col: b["value"]}
                                              for b in competitor_bars]
                                chart_result = pd.DataFrame(comp_rows)
                                chart_x      = "Entity"
                                chart_title_ = chart_title + " — Comparison"
                        except Exception:
                            pass  # fall back to raw result

                    if st.session_state[_ck] is None:
                        # ── Toast prompt ──────────────────────────────────────
                        st.markdown(
                            '<div class="chart-toast">📊 <b>Would you like to visualise this data?</b></div>',
                            unsafe_allow_html=True,
                        )
                        _live_cols = st.columns(len(_CHART_QUICK_OPTIONS))
                        for _lc, (_lbl, _ltypes) in zip(_live_cols, _CHART_QUICK_OPTIONS):
                            if _lc.button(_lbl, key=f"chartopt_{_lbl}_{_new_msg_idx}"):
                                st.session_state[_ck] = _ltypes or ALL_CHART_TYPES
                                st.rerun()
                    else:
                        # ── Charts shown ──────────────────────────────────────
                        _hcol, _ = st.columns([1.4, 8.6])
                        if _hcol.button("🙈 Hide", key=f"hide_chart_{_new_msg_idx}"):
                            st.session_state[_ck] = None
                            st.rerun()
                        try:
                            render_charts(chart_result, chart_x, y_col, chart_title_,
                                          selected_theme, chart_types=st.session_state[_ck])
                        except Exception as e:
                            st.warning(f"Chart generation note: {e}")

                # ── Step 5: Data table ────────────────────────────────────────
                result_df = None
                table_json = ""
                if result is not None and x_col:
                    if isinstance(result, pd.Series):
                        result_df = result.reset_index()
                    elif isinstance(result, pd.DataFrame):
                        result_df = result

                    if result_df is not None and len(result_df) > 0:
                        with st.expander("📋 Data Table"):
                            st.dataframe(result_df.head(50).reset_index(drop=True), use_container_width=True)
                        try:
                            table_json = result_df.head(50).to_json(
                                orient="split", date_format="iso"
                            )
                        except Exception:
                            table_json = ""

                # ── Step 6: Insight ───────────────────────────────────────────
                if insight:
                    st.markdown(
                        f'<div class="insight-box">💡 <b>Insight:</b> {insight}</div>',
                        unsafe_allow_html=True,
                    )

                # ── Step 7: Query code (collapsed) ────────────────────────────
                if code and x_col:
                    with st.expander("🔍 Query Code"):
                        st.code(code, language="python")

                # ── Save to history ───────────────────────────────────────────
                st.session_state.messages.append({
                    "role":             "assistant",
                    "content":          answer,
                    "insight":          insight,
                    "table_json":       table_json,
                    "code":             code,
                    "x_col":            x_col,
                    "y_col":            y_col,
                    "chart_title":      chart_title,
                    "wants_graph":      wants_graph,
                    "has_charts":       has_charts,
                    "competitor_bars":  competitor_bars,
                    "web_sources":      web_sources,
                })
                # _ck / _new_msg_idx already primed in Step 4 above

            except Exception as exc:
                st.error(f"❌ Error: {exc}")
                with st.expander("Debug traceback"):
                    st.code(traceback.format_exc())

    # Scroll to bottom after new content is rendered
    _components.html(
        "<script>window.parent.document.querySelector("
        "'[data-testid=\"stAppViewContainer\"] > .main').scrollTo(0, 99999);</script>",
        height=0,
    )


# ── Chat input ─────────────────────────────────────────────────────────────────
chat_input = st.chat_input(
    "Ask about your FY26 data…  e.g. 'Which country had the highest revenue in Feb-26?'"
)

# Example button takes priority over chat input
if st.session_state.example_q:
    q = st.session_state.example_q
    st.session_state.example_q = None
    process(q)
elif chat_input:
    process(chat_input)
