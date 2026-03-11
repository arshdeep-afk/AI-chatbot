"""
data_loader.py
Loads the FY26 Excel sheet and transforms it from wide format to long format.

Excel structure:
  Row 0  — Period labels: "Apr-25 FY26", "May-25 FY26", ..., "YTD", "FY", "Q1"...
  Row 1  — Pre-calculated subtotals (ignored)
  Row 2  — Date stamps (ignored)
  Row 3  — Column labels: "Sales Director", "Country", "Category", "Sub Category",
             then repeating "Units", "ASP", "Value", "GM" for each period
  Row 4+ — Data rows
"""

import io
import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ── Paths & constants ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
EXCEL_PATH = BASE_DIR / "TL International Business Dashboard_LIVE_v2.3 ALL Products_Feb-26_020326.xlsx"

DIM_COLS      = ["Sales Director", "Country", "Category", "Sub Category"]
METRICS       = ["Units", "ASP", "Value", "GM"]
ACTUAL_MONTHS = [
    "Apr-25", "May-25", "Jun-25", "Jul-25", "Aug-25", "Sep-25",
    "Oct-25", "Nov-25", "Dec-25", "Jan-26", "Feb-26", "Mar-26",
]
AGGREGATE_PERIODS = ["YTD", "FY", "Q1", "Q2", "Q3", "Q4", "H1", "H2"]

_MONTH_RE = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\s\-]?(\d{2})\b",
    re.IGNORECASE,
)

# ── Period label parser ────────────────────────────────────────────────────────
def _parse_period(raw: str) -> Optional[str]:
    """Extract canonical period label from a raw header cell value.

    Examples
    --------
    "Apr-25 FY26"  →  "Apr-25"
    "YTD"          →  "YTD"
    "Q1"           →  "Q1"
    """
    s = str(raw).strip()
    s_up = s.upper()

    # Check aggregate labels first (longest match first to avoid FY inside FY26)
    for agg in ["YTD", "H1", "H2", "Q1", "Q2", "Q3", "Q4", "FY"]:
        if s_up.startswith(agg) and (len(s_up) == len(agg) or not s_up[len(agg)].isalnum()):
            return agg

    # Match "MonYY" or "Mon-YY"
    m = _MONTH_RE.search(s)
    if m:
        mon = m.group(1).capitalize()[:3]
        yr  = m.group(2)
        return f"{mon}-{yr}"

    return None


# ── Column name builder ────────────────────────────────────────────────────────
def _build_col_names(row0: list, row3: list) -> list:
    """Combine row-0 period labels with row-3 metric labels into column names."""
    cols: list = []
    current_period: Optional[str] = None

    for i, (r0, r3) in enumerate(zip(row0, row3)):
        r0_s = str(r0).strip() if pd.notna(r0) else ""
        r3_s = str(r3).strip() if pd.notna(r3) else ""

        # Update current period if row-0 has a new non-empty label
        if r0_s and r0_s not in ("nan", ""):
            p = _parse_period(r0_s)
            if p:
                current_period = p

        if r3_s in DIM_COLS:
            cols.append(r3_s)
        elif r3_s in METRICS and current_period:
            cols.append(f"{current_period}_{r3_s}")
        else:
            cols.append(f"__drop_{i}__")

    return cols


# ── Wide loader ────────────────────────────────────────────────────────────────
def load_fy26_wide() -> pd.DataFrame:
    """Load FY26 sheet as a wide-format DataFrame with clean column names."""
    raw = pd.read_excel(EXCEL_PATH, sheet_name="FY26", header=None)

    col_names = _build_col_names(raw.iloc[0].tolist(), raw.iloc[3].tolist())

    df = raw.iloc[4:].copy()
    df.columns = col_names

    # Drop helper columns
    keep = [c for c in col_names if not c.startswith("__drop_")]
    df = df[[c for c in keep if c in df.columns]].copy()

    # Normalise dimension text
    for col in DIM_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # Drop empty / header-bleed rows
    df = df[df["Country"].notna()]
    df = df[~df["Country"].isin(["", "nan", "None", "NaN"])]
    df = df[df["Country"].str.len() > 0]

    # Convert every non-dimension column to numeric
    for col in [c for c in df.columns if c not in DIM_COLS]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df.reset_index(drop=True)


# ── Wide loader from bytes (uploaded files) ────────────────────────────────────
def load_fy26_wide_from_bytes(file_bytes: bytes) -> pd.DataFrame:
    """Load the FY26 sheet from raw bytes (e.g. a Streamlit uploaded file)."""
    raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name="FY26", header=None)

    col_names = _build_col_names(raw.iloc[0].tolist(), raw.iloc[3].tolist())

    df = raw.iloc[4:].copy()
    df.columns = col_names

    keep = [c for c in col_names if not c.startswith("__drop_")]
    df = df[[c for c in keep if c in df.columns]].copy()

    for col in DIM_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    df = df[df["Country"].notna()]
    df = df[~df["Country"].isin(["", "nan", "None", "NaN"])]
    df = df[df["Country"].str.len() > 0]

    for col in [c for c in df.columns if c not in DIM_COLS]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df.reset_index(drop=True)


# ── Melt to long ───────────────────────────────────────────────────────────────
def melt_to_long(df_wide: pd.DataFrame, include_aggregates: bool = False) -> pd.DataFrame:
    """Convert wide FY26 DataFrame to long format.

    Returns one row per (Sales Director, Country, Category, Sub Category, Month).
    Only rows where at least one metric is non-zero are kept.
    """
    periods = ACTUAL_MONTHS + (AGGREGATE_PERIODS if include_aggregates else [])
    frames = []

    for period in periods:
        avail = {
            f"{period}_{m}": m
            for m in METRICS
            if f"{period}_{m}" in df_wide.columns
        }
        if not avail:
            continue

        sub = df_wide[DIM_COLS + list(avail.keys())].copy()
        sub = sub.rename(columns=avail)
        sub["Month"] = period
        frames.append(sub)

    if not frames:
        return pd.DataFrame(columns=DIM_COLS + ["Month"] + METRICS)

    df_long = pd.concat(frames, ignore_index=True)
    df_long = df_long[df_long[METRICS].abs().sum(axis=1) > 0]
    return df_long.reset_index(drop=True)


# ── Module-level cache ─────────────────────────────────────────────────────────
_cache: dict = {}


def get_wide() -> pd.DataFrame:
    if "wide" not in _cache:
        _cache["wide"] = load_fy26_wide()
    return _cache["wide"]


def get_long() -> pd.DataFrame:
    """Actual monthly data only (Apr-25 … Mar-26)."""
    if "long" not in _cache:
        _cache["long"] = melt_to_long(get_wide())
    return _cache["long"]


def get_long_with_agg() -> pd.DataFrame:
    """All periods: actual months + YTD / FY / Q1-Q4 / H1-H2."""
    if "long_agg" not in _cache:
        _cache["long_agg"] = melt_to_long(get_wide(), include_aggregates=True)
    return _cache["long_agg"]


def get_schema_info() -> str:
    """Return a human-readable schema string for the AI system prompt."""
    return get_schema_info_from_dfs(get_long(), get_long_with_agg())


def get_schema_info_from_dfs(df: pd.DataFrame, df_all: pd.DataFrame) -> str:
    """Return a human-readable schema string computed from already-loaded DataFrames."""
    directors = sorted(df["Sales Director"].dropna().unique())
    countries  = sorted(df["Country"].dropna().unique())
    categories = sorted(df["Category"].dropna().unique())
    subcats    = sorted(df["Sub Category"].dropna().unique())

    actual = [m for m in ACTUAL_MONTHS if m in df["Month"].unique()]
    agg    = [m for m in AGGREGATE_PERIODS if m in df_all["Month"].unique()]

    return f"""Sales Dataset (EUR thousands)

TWO DataFrames are available in the execution namespace:
  df      — actual monthly data only
  df_all  — all periods including YTD, FY, Q1, Q2, Q3, Q4, H1, H2

COLUMNS (same in both):
  Sales Director  : {list(directors)}
  Country         : {len(countries)} countries (use case-insensitive matching)
  Category        : {list(categories)}
  Sub Category    : {list(subcats)}
  Month           : actual → {actual}
                    aggregates → {agg}
  Units           : units sold
  ASP             : average selling price (EUR)
  Value           : revenue (EUR thousands)
  GM              : gross margin (EUR thousands)

TOTAL ROWS (df): {len(df):,}"""
