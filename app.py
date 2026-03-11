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
from ai.query_parser import parse_query

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
    st.markdown("### ⚙️ API Key")
    if os.getenv("ANTHROPIC_API_KEY"):
        st.success("API key configured", icon="🔑")
    else:
        api_key_input = st.text_input(
            "Anthropic API Key",
            type="password",
            help="Get yours at console.anthropic.com",
        )
        if api_key_input:
            os.environ["ANTHROPIC_API_KEY"] = api_key_input

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

# ── Chart tab labels ───────────────────────────────────────────────────────────
_CHART_TAB_LABELS = {
    "bar":         "Bar",
    "hbar":        "H. Bar",
    "pie":         "Pie",
    "line":        "Line",
    "grouped_bar": "Grouped",
    "treemap":     "Treemap",
}


def render_charts(result, x_col, y_col, title, theme):
    """Generate all applicable chart types and display them in clickable tabs."""
    charts = auto_charts(
        result,
        x_col=x_col,
        y_col=y_col,
        title=title,
        chart_types=ALL_CHART_TYPES,
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

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            # Re-render charts from stored data
            if msg.get("table_json") and msg.get("x_col"):
                try:
                    tbl = pd.read_json(msg["table_json"], orient="split")
                    render_charts(tbl, msg["x_col"], msg["y_col"],
                                  msg.get("chart_title", ""), selected_theme)
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
            # Re-render code
            if msg.get("code"):
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
                parsed      = parse_query(question, schema_info, history)
                answer      = parsed.get("answer", "")
                code        = parsed.get("query_code", "")
                x_col       = parsed.get("x_col")
                y_col       = parsed.get("y_col")
                chart_title = parsed.get("chart_title", question[:60])
                insight     = parsed.get("insight", "")

                # ── Step 2: Execute generated pandas code ─────────────────────
                result, err = None, ""
                if code:
                    result, err = execute_query(code, df, df_all)

                # ── Step 3: Display text answer ───────────────────────────────
                st.markdown(f"**{answer}**")
                if err:
                    st.warning(f"ℹ️ Query note: {err}")

                # ── Step 4: Charts (tabbed) ───────────────────────────────────
                if result is not None:
                    try:
                        render_charts(result, x_col, y_col, chart_title, selected_theme)
                    except Exception as e:
                        st.warning(f"Chart generation note: {e}")

                # ── Step 5: Data table ────────────────────────────────────────
                result_df = None
                table_json = ""
                if result is not None:
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
                if code:
                    with st.expander("🔍 Query Code"):
                        st.code(code, language="python")

                # ── Save to history ───────────────────────────────────────────
                st.session_state.messages.append({
                    "role":        "assistant",
                    "content":     f"**{answer}**",
                    "insight":     insight,
                    "table_json":  table_json,
                    "code":        code,
                    "x_col":       x_col,
                    "y_col":       y_col,
                    "chart_title": chart_title,
                })

            except Exception as exc:
                st.error(f"❌ Error: {exc}")
                with st.expander("Debug traceback"):
                    st.code(traceback.format_exc())


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
