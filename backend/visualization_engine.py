"""
visualization_engine.py
Generates Plotly charts from a pandas query result.
Supports user-selected chart types and color themes.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ── Color themes ───────────────────────────────────────────────────────────────
COLOR_THEMES: Dict[str, List[str]] = {
    "Bright": [
        "#E63946",  # vivid red
        "#2DC653",  # vivid green
        "#1E90FF",  # vivid blue
        "#FFD700",  # vivid yellow
        "#FF7700",  # vivid orange
        "#9B5DE5",  # vivid purple
        "#00B4D8",  # vivid cyan
        "#FF006E",  # vivid pink
        "#FB5607",  # bright orange-red
        "#8338EC",  # bright violet
        "#3A86FF",  # bright azure
        "#06D6A0",  # vivid teal
    ],
    "Corporate Blue": [
        "#1f4e79", "#2e75b6", "#4472c4", "#70ad47",
        "#ed7d31", "#ffc000", "#c00000", "#7030a0",
        "#00b0f0", "#ff0000", "#92d050", "#ff66cc",
    ],
    "Vibrant": [
        "#E63946", "#F4A261", "#2A9D8F", "#264653",
        "#E9C46A", "#6A4C93", "#1982C4", "#8AC926",
        "#FF595E", "#FFCA3A", "#6A4C93", "#1982C4",
    ],
    "Colorblind Safe": [
        "#E69F00", "#56B4E9", "#009E73", "#0072B2",
        "#D55E00", "#CC79A7", "#F0E442", "#000000",
        "#999999", "#E69F00", "#56B4E9", "#009E73",
    ],
    "Dark Professional": [
        "#003049", "#D62828", "#F77F00", "#FCBF49",
        "#EAE2B7", "#4CC9F0", "#7209B7", "#3A0CA3",
        "#480CA8", "#560BAD", "#B5179E", "#F72585",
    ],
    "Pastel": [
        "#FFB3BA", "#FFDFBA", "#FFFFBA", "#BAFFC9",
        "#BAE1FF", "#D4BAFF", "#FFB3F7", "#B3FFF9",
        "#FFC9BA", "#E8FFBA", "#BAD4FF", "#FFBAF5",
    ],
}

ALL_CHART_TYPES = ["Bar", "Horizontal Bar", "Pie / Donut", "Line Trend", "Grouped Bar", "Treemap"]

_MONTH_ORDER = [
    "Apr-25", "May-25", "Jun-25", "Jul-25", "Aug-25", "Sep-25",
    "Oct-25", "Nov-25", "Dec-25", "Jan-26", "Feb-26", "Mar-26",
]

_BASE_LAYOUT = dict(
    plot_bgcolor="white",
    paper_bgcolor="white",
    font=dict(family="Arial", size=13, color="#222222"),
    title_font=dict(size=16, color="#111111", family="Arial Black"),
    margin=dict(l=50, r=30, t=65, b=80),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)


def _to_df(result) -> Optional[pd.DataFrame]:
    if isinstance(result, pd.Series):
        df = result.reset_index()
        if len(df.columns) == 2:
            df.columns = [str(df.columns[0]), "Value"]
        return df
    if isinstance(result, pd.DataFrame):
        return result.copy()
    try:
        return pd.DataFrame({"Result": [result]})
    except Exception:
        return None


def _sort_by_month(df: pd.DataFrame, x_col: str) -> pd.DataFrame:
    if df[x_col].isin(_MONTH_ORDER).all():
        sort_map = {m: i for i, m in enumerate(_MONTH_ORDER)}
        df = df.copy()
        df["__s"] = df[x_col].map(sort_map)
        df = df.sort_values("__s").drop(columns="__s")
    return df


def auto_charts(
    result,
    x_col: str = None,
    y_col: str = None,
    title: str = "Analysis Result",
    max_rows: int = 20,
    chart_types: List[str] = None,
    color_theme: str = "Bright",
) -> List[Tuple[str, go.Figure]]:
    """
    Generate Plotly charts from a query result.

    Parameters
    ----------
    chart_types : list of strings from ALL_CHART_TYPES the user wants shown.
                  Defaults to ["Bar", "Pie / Donut"] when None.
    color_theme : key from COLOR_THEMES dict.
    """
    if chart_types is None:
        chart_types = ["Bar", "Pie / Donut"]

    colors = COLOR_THEMES.get(color_theme, COLOR_THEMES["Corporate Blue"])

    df = _to_df(result)
    if df is None or len(df) == 0:
        return []

    df = df.head(max_rows)
    num_cols = df.select_dtypes(include=np.number).columns.tolist()
    str_cols = df.select_dtypes(include="object").columns.tolist()

    if x_col not in df.columns:
        x_col = str_cols[0] if str_cols else df.columns[0]
    if y_col not in df.columns:
        y_col = num_cols[0] if num_cols else df.columns[-1]

    n = len(df)
    is_monthly = (
        x_col == "Month"
        or (
            df[x_col].dtype == object
            and df[x_col]
            .str.contains(
                r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",
                case=False, na=False, regex=True,
            )
            .any()
        )
    )

    charts: List[Tuple[str, go.Figure]] = []

    # ── Bar (vertical) ─────────────────────────────────────────────────────────
    if "Bar" in chart_types:
        try:
            fig = px.bar(
                df, x=x_col, y=y_col,
                title=title,
                color=x_col,                         # each bar its own colour
                color_discrete_sequence=colors,
                text_auto=".3s",
            )
            fig.update_layout(**_BASE_LAYOUT, showlegend=False)
            fig.update_traces(
                textposition="outside",
                cliponaxis=False,
                textfont=dict(size=12, color="#111111"),
            )
            fig.update_xaxes(
                tickangle=-35,
                tickfont=dict(size=11, color="#222222"),
                title_font=dict(size=13, color="#222222"),
            )
            fig.update_yaxes(
                tickfont=dict(size=11, color="#222222"),
                title_font=dict(size=13, color="#222222"),
            )
            charts.append(("bar", fig))
        except Exception:
            pass

    # ── Horizontal Bar ─────────────────────────────────────────────────────────
    if "Horizontal Bar" in chart_types:
        try:
            df_h = df.sort_values(y_col, ascending=True).tail(20)
            fig = px.bar(
                df_h, x=y_col, y=x_col,
                orientation="h",
                title=f"{title} — Horizontal",
                color=x_col,
                color_discrete_sequence=colors,
                text_auto=".3s",
            )
            fig.update_layout(**_BASE_LAYOUT, showlegend=False,
                              margin=dict(l=110, r=30, t=65, b=50))
            fig.update_traces(
                textposition="outside",
                cliponaxis=False,
                textfont=dict(size=12, color="#111111"),
            )
            fig.update_xaxes(
                tickfont=dict(size=11, color="#222222"),
                title_font=dict(size=13, color="#222222"),
            )
            fig.update_yaxes(
                tickfont=dict(size=11, color="#222222"),
                title_font=dict(size=13, color="#222222"),
            )
            charts.append(("hbar", fig))
        except Exception:
            pass

    # ── Pie / Donut ────────────────────────────────────────────────────────────
    if "Pie / Donut" in chart_types and y_col in df.columns:
        try:
            top = df.nlargest(12, y_col) if n > 12 else df
            fig = px.pie(
                top, names=x_col, values=y_col,
                title=f"{title} — Share",
                hole=0.38,
                color_discrete_sequence=colors,
            )
            fig.update_traces(
                textposition="outside",
                textinfo="percent+label",
                textfont=dict(size=12, color="#111111"),
                pull=[0.03] * len(top),
            )
            fig.update_layout(**_BASE_LAYOUT)
            charts.append(("pie", fig))
        except Exception:
            pass

    # ── Line Trend ─────────────────────────────────────────────────────────────
    if "Line Trend" in chart_types:
        try:
            df_l = _sort_by_month(df, x_col) if is_monthly else df
            color_col = str_cols[1] if len(str_cols) > 1 and str_cols[1] != x_col else None
            fig = px.line(
                df_l, x=x_col, y=y_col,
                color=color_col,
                title=f"{title} — Trend",
                markers=True,
                color_discrete_sequence=colors,
            )
            fig.update_layout(**_BASE_LAYOUT)
            fig.update_traces(line=dict(width=2.5), marker=dict(size=8))
            fig.update_xaxes(
                tickangle=-35,
                tickfont=dict(size=11, color="#222222"),
                title_font=dict(size=13, color="#222222"),
            )
            fig.update_yaxes(
                tickfont=dict(size=11, color="#222222"),
                title_font=dict(size=13, color="#222222"),
            )
            charts.append(("line", fig))
        except Exception:
            pass

    # ── Grouped Bar ────────────────────────────────────────────────────────────
    if "Grouped Bar" in chart_types and len(num_cols) >= 2:
        try:
            extra = [c for c in num_cols if c != y_col][:2]
            if extra:
                fig = px.bar(
                    df, x=x_col, y=[y_col] + extra,
                    title=f"{title} — Multi-Metric",
                    barmode="group",
                    color_discrete_sequence=colors,
                    text_auto=".2s",
                )
                fig.update_layout(**_BASE_LAYOUT)
                fig.update_xaxes(
                    tickangle=-35,
                    tickfont=dict(size=11, color="#222222"),
                    title_font=dict(size=13, color="#222222"),
                )
                fig.update_yaxes(
                    tickfont=dict(size=11, color="#222222"),
                    title_font=dict(size=13, color="#222222"),
                )
                fig.update_traces(textfont=dict(size=11, color="#111111"))
                charts.append(("grouped_bar", fig))
        except Exception:
            pass

    # ── Treemap ────────────────────────────────────────────────────────────────
    if "Treemap" in chart_types and y_col in df.columns:
        try:
            fig = px.treemap(
                df, path=[x_col], values=y_col,
                title=f"{title} — Treemap",
                color=y_col,
                color_continuous_scale=["#d4e6f1", "#1f4e79"],
            )
            fig.update_layout(**_BASE_LAYOUT)
            fig.update_traces(textfont=dict(size=13))
            charts.append(("treemap", fig))
        except Exception:
            pass

    return charts
