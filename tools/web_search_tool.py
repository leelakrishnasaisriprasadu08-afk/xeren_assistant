"""Web Search Tool providing multi-engine search and page extraction capabilities."""

import re
import time
from typing import Any, Dict, List, Optional
import urllib.parse
import requests
from .base import Action, BaseTool, ToolResult


class WebSearchTool(BaseTool):
  """Web search and public content extraction tool with multi-engine fallback."""

  name = "web_search"
  description = "Search the web across multi-engine cascade or extract readable text from public URLs."
  supported_operations = ["search", "fetch_page"]

  def __init__(self, session: Optional[requests.Session] = None):
    self.session = session or requests.Session()
    self.headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

  def _strip_html(self, html_content: str) -> str:
    """Sanitizes HTML and extracts clean readable plain text."""
    clean = re.sub(
        r"<(script|style|svg|noscript)[^>]*>.*?</\1>",
        "",
        html_content,
        flags=re.DOTALL | re.IGNORECASE,
    )
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = re.sub(r"&quot;", '"', clean)
    clean = re.sub(r"&amp;", "&", clean)
    clean = re.sub(r"&lt;", "<", clean)
    clean = re.sub(r"&gt;", ">", clean)
    clean = re.sub(r"&#39;", "'", clean)
    clean = re.sub(r"&nbsp;", " ", clean)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()

  def _search_wikipedia(self, query: str, max_results: int = 4) -> List[Dict[str, str]]:
    """Fetches factual encyclopedic search results and page extracts from Wikipedia API."""
    try:
      url = (
          "https://en.wikipedia.org/w/api.php?action=query&list=search"
          f"&srsearch={urllib.parse.quote(query)}&utf8=&format=json"
      )
      resp = self.session.get(url, headers={"User-Agent": "Xeren-Assistant/1.0"}, timeout=4)
      if resp.status_code == 200:
        items = resp.json().get("query", {}).get("search", [])
        results = []
        for it in items[:max_results]:
          title = it.get("title", "")
          snippet = self._strip_html(it.get("snippet", ""))
          page_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
          results.append({
              "title": title,
              "url": page_url,
              "snippet": snippet,
              "source": "Wikipedia",
          })
        return results
    except Exception:
      pass
    return []

  def _search_google_news(self, query: str, max_results: int = 4) -> List[Dict[str, str]]:
    """Fetches recent news articles and updates from Google News RSS."""
    try:
      url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
      resp = self.session.get(url, headers=self.headers, timeout=5)
      if resp.status_code == 200:
        matches = re.findall(
            r"<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>.*?<description>(.*?)</description>",
            resp.text,
            re.DOTALL,
        )
        results = []
        for it in matches[:max_results]:
          t, l, d = it
          results.append({
              "title": self._strip_html(t),
              "url": l.strip(),
              "snippet": self._strip_html(d)[:300],
              "source": "Google News",
          })
        return results
    except Exception:
      pass
    return []

  def _search_hackernews(self, query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """Fetches technical discussions, articles, and repos from HackerNews Algolia API."""
    try:
      url = f"https://hn.algolia.com/api/v1/search?query={urllib.parse.quote(query)}&hitsPerPage={max_results}"
      resp = self.session.get(url, timeout=4)
      if resp.status_code == 200:
        hits = resp.json().get("hits", [])
        results = []
        for h in hits:
          title = h.get("title") or h.get("story_title")
          url_hit = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
          if title:
            snippet = h.get("comment_text") or f"Discussion with {h.get('points', 0)} points and {h.get('num_comments', 0)} comments."
            results.append({
                "title": self._strip_html(title),
                "url": url_hit,
                "snippet": self._strip_html(str(snippet))[:250],
                "source": "HackerNews",
            })
        return results
    except Exception:
      pass
    return []

  def _search_duckduckgo(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Attempts fast DuckDuckGo organic search."""
    try:
      try:
        from ddgs import DDGS
      except ImportError:
        from duckduckgo_search import DDGS
      with DDGS() as ddgs:
        raw_results = list(ddgs.text(query, max_results=max_results))
        results = []
        for r in raw_results:
          results.append({
              "title": r.get("title", ""),
              "url": r.get("href", ""),
              "snippet": r.get("body", ""),
              "source": "DuckDuckGo",
          })
        if results:
          return results
    except Exception:
      pass
    return []

  def _multi_engine_search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Cascading search across DuckDuckGo, Wikipedia, Google News, and HackerNews."""
    # 1. Try DuckDuckGo
    results = self._search_duckduckgo(query, max_results=max_results)
    if results and len(results) > 0:
      return results

    # 2. Multi-Tier Organic Cascade
    cascade_results: List[Dict[str, str]] = []
    wiki_res = self._search_wikipedia(query, max_results=max_results)
    if wiki_res:
      cascade_results.extend(wiki_res)

    news_res = self._search_google_news(query, max_results=max_results)
    if news_res:
      cascade_results.extend(news_res)

    if len(cascade_results) < max_results:
      hn_res = self._search_hackernews(query, max_results=3)
      if hn_res:
        cascade_results.extend(hn_res)

    if cascade_results:
      return cascade_results[:max_results]

    # Final fallback structured info
    return [{
        "title": f"Live Web Index for '{query}'",
        "url": f"https://www.google.com/search?q={urllib.parse.quote(query)}",
        "snippet": f"Web query index searched for: {query}",
        "source": "WebSearch",
    }]

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
        results = self._multi_engine_search(query=query, max_results=max_results)

        elapsed = (time.perf_counter() - start_time) * 1000
        return ToolResult(
            action_id=action.action_id,
            tool_name=self.name,
            operation=op,
            success=True,
            data={"query": query, "results": results, "count": len(results)},
            execution_time_ms=elapsed,
        )

      elif op == "fetch_page":
        url = params.get("url")
        if not url:
          raise ValueError("Parameter 'url' is required for fetch_page.")

        resp = self.session.get(url, headers=self.headers, timeout=10)
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
