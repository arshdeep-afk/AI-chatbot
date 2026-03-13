"""
query_engine.py
Safe execution of AI-generated pandas code.
"""

import re
from typing import Any, Tuple

import numpy as np
import pandas as pd

# Regex for dangerous patterns
_DANGER = re.compile(
    r"\b(import|exec|eval|open|os|sys|subprocess|shutil|pathlib|"
    r"__import__|__builtins__|getattr|setattr|delattr|"
    r"globals|locals|vars|dir|compile)\b"
)

# Safe import lines Claude may add despite the system prompt saying they're unnecessary
_SAFE_IMPORT = re.compile(
    r"^\s*(import\s+(pandas|numpy)(\s+as\s+\w+)?|from\s+(pandas|numpy)\s+import\s+\S+)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def _strip_safe_imports(code: str) -> str:
    """Remove pandas/numpy import lines — already available in the execution namespace."""
    return _SAFE_IMPORT.sub("", code)


def validate_code(code: str) -> Tuple[bool, str]:
    """Return (is_safe, reason). Rejects obviously dangerous patterns."""
    m = _DANGER.search(code)
    if m:
        return False, f"Blocked keyword '{m.group()}' in generated code"
    return True, ""


def execute_query(code: str, df: pd.DataFrame, df_all: pd.DataFrame = None) -> Tuple[Any, str]:
    """Execute AI-generated pandas code in a restricted namespace.

    The code must assign its final answer to a variable named ``result``.

    Parameters
    ----------
    code    : Python/pandas code string
    df      : actual monthly DataFrame
    df_all  : DataFrame with aggregate periods (optional; defaults to df)

    Returns
    -------
    (result, error_message)  — result is None when an error occurs.
    """
    if not code or not code.strip():
        return None, "No query code provided"

    code = _strip_safe_imports(code)
    safe, reason = validate_code(code)
    if not safe:
        return None, f"Code validation failed: {reason}"

    ns: dict = {
        "df":     df.copy(),
        "df_all": (df_all if df_all is not None else df).copy(),
        "pd":     pd,
        "np":     np,
    }

    try:
        exec(compile(code, "<ai_query>", "exec"), ns)
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"

    result = ns.get("result")
    if result is None:
        return None, "Query did not assign to a variable named 'result'"

    return result, ""
