"""
query_parser.py
Sends user questions to Claude Opus 4.6 and returns a structured query plan.
"""

import json
import os
import re
from typing import Optional

import anthropic
from dotenv import load_dotenv

from ai.prompt_templates import SYSTEM_PROMPT
from ai.web_search import needs_web_search, search_competitor_data

load_dotenv()

_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to a .env file or enter it in the sidebar."
            )
        _client = anthropic.Anthropic(api_key=key)
    return _client


def parse_query(
    question: str,
    schema_info: str,
    history: list = None,
) -> dict:
    """Send a user question to Claude and return a structured query plan.

    Returns a dict with keys:
        answer, query_code, x_col, y_col, chart_type, chart_title, insight
    """
    client = _get_client()

    messages = []
    if history:
        # Include last 3 user-assistant pairs for context
        messages.extend(history[-6:])

    user_content = f"SCHEMA:\n{schema_info}\n\nQUESTION: {question}"

    # Enrich with live web search results when competitor/external data is needed
    web_sources: list = []
    if needs_web_search(question):
        web_snippets, web_sources = search_competitor_data(question)
        if web_snippets:
            user_content += (
                "\n\n─── LIVE WEB SEARCH RESULTS (use these for competitor context) ───\n"
                + web_snippets
                + "\n─── END WEB SEARCH RESULTS ───"
            )

    messages.append({"role": "user", "content": user_content})

    # Stream with adaptive thinking (Opus 4.6 recommended approach)
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=messages,
    ) as stream:
        final = stream.get_final_message()

    # Extract the text block (skip thinking blocks)
    raw_text = ""
    for block in final.content:
        if block.type == "text":
            raw_text = block.text.strip()
            break

    result = _parse_json(raw_text)
    # Attach web sources so app.py can display them as clickable links
    result["_web_sources"] = web_sources
    return result


def generate_data_answer(
    question: str,
    result,
    preliminary_answer: str = "",
    preliminary_insight: str = "",
) -> tuple:
    """Generate a data-aware answer + insight using actual query results.

    Makes a fast Haiku call with the real result rows so the response
    contains specific numbers, names, and percentages.
    Returns (answer, insight) — falls back to preliminary values on failure.
    """
    import pandas as pd

    client = _get_client()

    if isinstance(result, pd.Series):
        result_df = result.reset_index()
    elif isinstance(result, pd.DataFrame):
        result_df = result.copy()
    else:
        return preliminary_answer, preliminary_insight

    row_count = len(result_df)
    sample_str = result_df.head(20).to_string(index=False)

    prompt = (
        f'User question: "{question}"\n\n'
        f"Query returned {row_count} row(s). Internal data sample:\n{sample_str}\n\n"
        "Write a response that combines the internal data above with any relevant "
        "competitor/industry knowledge you have (citing source + period in parentheses).\n"
        "1. answer — 3-5 sentences. Lead with the specific internal finding (numbers, names). "
        "Then add competitor or industry context if the question calls for it. "
        "Use **bold** for key figures and names. Sound like a knowledgeable analyst colleague.\n"
        "2. insight — 2-3 sentences with concrete percentages, comparisons, or business "
        "implications. If comparing to competitors, note data currency.\n\n"
        'Return VALID JSON only: {"answer": "...", "insight": "..."}'
    )

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()
        parsed = json.loads(text)
        return (
            parsed.get("answer", preliminary_answer),
            parsed.get("insight", preliminary_insight),
        )
    except Exception:
        return preliminary_answer, preliminary_insight


def _parse_json(text: str) -> dict:
    """Robustly parse JSON from Claude's response."""
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract a JSON object from within surrounding text
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass

    # Fallback
    return {
        "answer": (
            "I wasn't able to generate a structured response for that question. "
            "This usually means the question is outside the scope of the FY26 sales dataset "
            "(e.g. external company data, internet sources, or non-sales topics). "
            "Try asking about revenue, units, gross margin, countries, categories, or sales directors."
        ),
        "query_code": "",
        "x_col": None,
        "y_col": None,
        "chart_type": "bar",
        "chart_title": "Result",
        "insight": "",
    }
