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

    messages.append({
        "role": "user",
        "content": f"SCHEMA:\n{schema_info}\n\nQUESTION: {question}",
    })

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

    return _parse_json(raw_text)


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
        "answer": "I couldn't parse the response. Please rephrase your question.",
        "query_code": "",
        "x_col": None,
        "y_col": None,
        "chart_type": "bar",
        "chart_title": "Result",
        "insight": "",
    }
