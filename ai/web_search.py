"""
web_search.py
Optional Tavily web search for competitor / external market data.
Only activates when TAVILY_API_KEY is set and the question mentions
competitor companies, external benchmarks, or vague comparison intent.
"""

import os
import re
from typing import Optional

_tavily_client = None

# ── Specific competitor / company names ────────────────────────────────────────
_COMPANY_TERMS = [
    "medtronic", "abbott", "boston scientific", "b. braun", "braun",
    "terumo", "stryker", "edwards", "becton", "bd ", "zimmer", "biomet",
    "philips", "siemens healthineers", "ge healthcare", "olympus",
]

# ── Vague comparison / benchmarking intent triggers ────────────────────────────
_VAGUE_TERMS = [
    "competitor", "competition", "benchmark", "industry average",
    "market share", "market size", "vs market", "against market",
    "publicly available", "external data", "other compan",
    "similar compan", "similar domain", "publicly traded",
    "how do we compare", "how are we doing", "are we competitive",
    "industry standard", "sector average", "market leader", "market trend",
    "compare us", "how does our", "industry trend", "typical for",
    "peer compan", "rival", "in the market", "market norm",
    "how does that compare", "is that good", "is that normal",
]

_COMPETITOR_TERMS = _COMPANY_TERMS + _VAGUE_TERMS

# ── Domain context injected when no specific company is named ──────────────────
_DOMAIN_CONTEXT = (
    "medical device cardiovascular interventional cardiology "
    "DCB drug coated balloon DES drug eluting stent PTCA catheter market"
)

# Words to strip when extracting query intent
_STOPWORDS = {
    "the", "a", "an", "of", "in", "and", "or", "to", "for", "is", "are",
    "our", "we", "my", "how", "what", "who", "when", "where", "why",
    "do", "does", "did", "that", "this", "it", "with", "vs", "us", "be",
    "has", "have", "had", "was", "were", "can", "could", "would", "should",
}


def needs_web_search(question: str) -> bool:
    """Return True if the question likely needs live external data."""
    q = question.lower()
    return any(t in q for t in _COMPETITOR_TERMS)


def _build_search_query(question: str) -> str:
    """Build a focused search query from the user question."""
    q = question.lower()

    # Extract specific company names mentioned
    companies = [t.strip() for t in _COMPANY_TERMS if t in q]

    if companies:
        # User named specific companies — target them directly
        company_str = " ".join(companies[:2])
        core = re.sub(r"\s+", " ", question[:150]).strip()
        return f"{company_str} revenue annual report financials 2024 2025 {core}"

    # Vague question — build a domain-specific benchmark query
    # Extract meaningful intent words from the question
    words = [w for w in re.findall(r"\b[a-z]{3,}\b", q) if w not in _STOPWORDS]
    intent = " ".join(words[:6])
    return (
        f"{_DOMAIN_CONTEXT} benchmark revenue market share industry average 2024 2025 {intent}"
    )


def search_competitor_data(
    question: str, max_results: int = 4
) -> tuple[Optional[str], list[dict]]:
    """
    Run a Tavily web search for competitor/industry context.

    Returns a tuple:
      - formatted string of search results to inject into the AI prompt (or None)
      - list of source dicts: [{"title": ..., "url": ...}]
    """
    global _tavily_client

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return None, []

    try:
        from tavily import TavilyClient  # lazy import — only needed when key is set
        if _tavily_client is None:
            _tavily_client = TavilyClient(api_key=api_key)

        query = _build_search_query(question)
        response = _tavily_client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
            include_answer=True,
        )

        parts: list[str] = []
        sources: list[dict] = []

        # Tavily's own synthesised answer (often the most useful part)
        if response.get("answer"):
            parts.append(f"**Web summary:** {response['answer']}")

        # Individual source snippets
        for i, r in enumerate(response.get("results", []), 1):
            title   = r.get("title", "")
            content = r.get("content", "")[:600].strip()
            url     = r.get("url", "")
            parts.append(f"\n[{i}] {title}\n{content}\nSource: {url}")
            if url:
                sources.append({"title": title or url, "url": url})

        return ("\n".join(parts) if parts else None), sources

    except Exception:
        return None, []
