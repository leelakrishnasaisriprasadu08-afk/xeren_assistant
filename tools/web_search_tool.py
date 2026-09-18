"""Web Search Tool providing search and page extraction capabilities."""

import re
import time
from typing import Any, Dict, List, Optional
import requests
from .base import Action, BaseTool, ToolResult


class WebSearchTool(BaseTool):
  """Web search and public content extraction tool."""

  name = "web_search"
  description = "Search the web for query terms or extract readable text from public URLs."
  supported_operations = ["search", "fetch_page"]

  def __init__(self, session: Optional[requests.Session] = None):
    self.session = session or requests.Session()

  def _strip_html(self, html_content: str) -> str:
    """Simple regex HTML stripper for readable text extraction."""
    # Remove script and style tags
    clean = re.sub(
        r"<(script|style)[^>]*>.*?</\1>",
        "",
        html_content,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Remove all HTML tags
    clean = re.sub(r"<[^>]+>", " ", clean)
    # Normalize multiple whitespace
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()

  async def execute(self, action: Action) -> ToolResult:
    start_time = time.perf_counter()
    op = action.operation.lower()
    params = action.parameters or {}

    try:
      if op == "search":
        query = params.get("query") or params.get("q")
        if not query:
          raise ValueError("Parameter 'query' is required for search.")

        max_results = min(int(params.get("max_results", 5)), 10)
        results = []

        try:
          from duckduckgo_search import DDGS
          with DDGS() as ddgs:
            raw_results = list(ddgs.text(query, max_results=max_results))
            for r in raw_results:
              results.append({
                  "title": r.get("title"),
                  "url": r.get("href"),
                  "snippet": r.get("body"),
              })
        except Exception as e:
          # Fallback if DDG service or library is unavailable
          results = [{
              "title": f"Search results for '{query}'",
              "url": f"https://duckduckgo.com/?q={query}",
              "snippet": f"Web query captured for: {query}",
          }]

        elapsed = (time.perf_counter() - start_time) * 1000
        return ToolResult(
            action_id=action.action_id,
            tool_name=self.name,
            operation=op,
            success=True,
            data={"query": query, "results": results},
            execution_time_ms=elapsed,
        )

      elif op == "fetch_page":
        url = params.get("url")
        if not url:
          raise ValueError("Parameter 'url' is required for fetch_page.")

        headers = {"User-Agent": "Xeren-Assistant/0.1.0 (Public Research Bot)"}
        resp = self.session.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        clean_text = self._strip_html(resp.text)
        max_chars = params.get("max_chars", 5000)

        elapsed = (time.perf_counter() - start_time) * 1000
        return ToolResult(
            action_id=action.action_id,
            tool_name=self.name,
            operation=op,
            success=True,
            data={
                "url": url,
                "text": clean_text[:max_chars],
                "total_length": len(clean_text),
            },
            execution_time_ms=elapsed,
        )

      else:
        raise ValueError(
            f"Unsupported operation '{op}' for tool '{self.name}'"
        )

    except Exception as e:
      elapsed = (time.perf_counter() - start_time) * 1000
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=op,
          success=False,
          error=str(e),
          execution_time_ms=elapsed,
      )
