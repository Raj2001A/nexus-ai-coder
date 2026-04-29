"""
doc_search.py
-------------
Documentation search tool for agents.

Provides web search capabilities so agents can look up API documentation,
error messages, and best practices while working on coding tasks.

Primary:  Tavily API (AI-optimized search engine)
Fallback: DuckDuckGo (no API key required)

Interview talking point:
    "I gave the agents access to documentation search with an automatic
     fallback chain. If the paid API is unavailable, it silently degrades
     to DuckDuckGo — the agent never gets a hard failure on search."
"""

import logging
from typing import Optional

from langchain_core.tools import tool
from backend.config import settings

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_RESULTS = 3             # Keep it small to save LLM tokens
MAX_CONTENT_LENGTH = 1500   # Truncate each result's content


def _search_with_tavily(query: str) -> Optional[str]:
    """
    Search using Tavily API (AI-optimized search engine).
    Returns formatted results or None if unavailable.
    """
    if not settings.tavily_api_key:
        logger.debug("[DocSearch] No Tavily API key configured — skipping.")
        return None

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=settings.tavily_api_key)
        response = client.search(
            query=query,
            search_depth="advanced",   # More thorough results
            max_results=MAX_RESULTS,
            include_answer=True,       # Get a synthesized answer
        )

        parts = []

        # Include Tavily's synthesized answer if available
        if response.get("answer"):
            parts.append(f"📝 Summary: {response['answer']}\n")

        # Include individual source results
        for i, result in enumerate(response.get("results", []), 1):
            title = result.get("title", "No title")
            url = result.get("url", "")
            content = result.get("content", "")

            # Truncate long content
            if len(content) > MAX_CONTENT_LENGTH:
                content = content[:MAX_CONTENT_LENGTH] + "..."

            parts.append(f"--- Source {i}: {title} ---\nURL: {url}\n{content}\n")

        return "\n".join(parts) if parts else None

    except ImportError:
        logger.warning("[DocSearch] tavily-python not installed.")
        return None
    except Exception as e:
        logger.warning(f"[DocSearch] Tavily search failed: {e}")
        return None


def _search_with_duckduckgo(query: str) -> Optional[str]:
    """
    Fallback search using DuckDuckGo (no API key required).
    Returns formatted results or None on failure.
    """
    try:
        from langchain_community.tools import DuckDuckGoSearchResults

        ddg = DuckDuckGoSearchResults(max_results=MAX_RESULTS)
        raw_results = ddg.invoke(query)

        if raw_results and isinstance(raw_results, str):
            return f"🔍 DuckDuckGo Results:\n{raw_results}"

        return None

    except ImportError:
        logger.warning("[DocSearch] DuckDuckGo search tool not available.")
        return None
    except Exception as e:
        logger.warning(f"[DocSearch] DuckDuckGo search failed: {e}")
        return None


def search_documentation(query: str) -> str:
    """
    Search the web for documentation, API references, and coding solutions.
    Tries Tavily first (better quality), falls back to DuckDuckGo.

    Args:
        query: Natural language search query.

    Returns:
        Formatted search results with source citations.
    """
    logger.info(f"[DocSearch] Searching: '{query[:60]}...'")

    # Try primary search engine (Tavily)
    result = _search_with_tavily(query)
    if result:
        logger.info("[DocSearch] Results from Tavily ✅")
        return result

    # Fallback to DuckDuckGo
    result = _search_with_duckduckgo(query)
    if result:
        logger.info("[DocSearch] Results from DuckDuckGo (fallback) ✅")
        return result

    # Both failed — return a helpful message
    return (
        "⚠️ Documentation search is currently unavailable.\n"
        "Neither Tavily nor DuckDuckGo returned results.\n"
        "Suggestion: Try rephrasing your query or check your API keys."
    )


# ── LangChain Tool (used by CrewAI agents) ─────────────────────────────────

@tool
def search_docs(query: str) -> str:
    """
    Search the web for programming documentation, API references,
    error explanations, and best practices.

    Use this when you need to:
    - Look up how to use a library or framework
    - Find the correct syntax for an API call
    - Debug an error message you don't recognize
    - Check best practices for a pattern

    Args:
        query: A specific technical question or search term.
              More specific queries give better results.
              Example: "Python FastAPI WebSocket streaming example"

    Returns:
        Relevant documentation excerpts with source URLs.
    """
    return search_documentation(query)
