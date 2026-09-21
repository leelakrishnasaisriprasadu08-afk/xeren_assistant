"""Web Search Tool providing multi-engine search, credibility scoring, and trusted automation target selection."""

import re
import time
from typing import Any, Dict, List, Optional
import urllib.parse
import requests
from .base import Action, BaseTool, ToolResult

# Canonical registry of verified authority domains with trust weights (max 40 pts)
TRUSTED_AUTHORITY_DOMAINS: Dict[str, tuple[str, int]] = {
    # Programming & Languages
    "python.org": ("Official Python Software Foundation", 40),
    "docs.python.org": ("Official Python Documentation", 40),
    "pypi.org": ("Official Python Package Index (PyPI)", 38),
    "github.com": ("Official Open-Source Code Repository", 36),
    "fastapi.tiangolo.com": ("Official FastAPI Framework Documentation", 40),
    "flask.palletsprojects.com": ("Official Flask Documentation", 40),
    "djangoproject.com": ("Official Django Project Documentation", 40),
    "pytest.org": ("Official Pytest Documentation", 38),
    "nodejs.org": ("Official Node.js Documentation", 38),
    "typescriptlang.org": ("Official TypeScript Documentation", 40),
    "react.dev": ("Official React Documentation", 40),
    "vuejs.org": ("Official Vue.js Documentation", 38),
    "angular.dev": ("Official Angular Documentation", 38),
    "developer.mozilla.org": ("MDN Web Docs (Mozilla Authority)", 40),
    "w3.org": ("W3C World Wide Web Consortium Standard", 40),
    "stackoverflow.com": ("Stack Overflow Developer Q&A", 32),
    # Cloud, DevOps & Systems
    "cloud.google.com": ("Google Cloud Platform Documentation", 38),
    "aws.amazon.com": ("Amazon Web Services Documentation", 38),
    "learn.microsoft.com": ("Microsoft Official Documentation", 38),
    "kubernetes.io": ("Official Kubernetes Documentation", 38),
    "docker.com": ("Official Docker Documentation", 38),
    # Reference & Scientific
    "en.wikipedia.org": ("Verified Reference Encyclopedia (Wikipedia)", 36),
    "wikipedia.org": ("Verified Reference Encyclopedia (Wikipedia)", 36),
    "arxiv.org": ("Cornell University Open-Access Scientific Research", 38),
    "nature.com": ("Nature Peer-Reviewed Journal", 40),
    "science.org": ("Science Academic Journal", 40),
    # Platforms & Professional Networks
    "linkedin.com": ("Official LinkedIn Platform Gateway", 40),
    "upwork.com": ("Official Upwork Marketplace Gateway", 40),
    "fiverr.com": ("Official Fiverr Platform Gateway", 40),
    # Verified News & Tech Syndicates
    "reuters.com": ("Reuters Global News Syndicate", 35),
    "apnews.com": ("Associated Press Verified News", 35),
    "bbc.com": ("BBC World News Authority", 35),
    "theguardian.com": ("The Guardian Verified Journalism", 32),
    "bloomberg.com": ("Bloomberg Financial News Authority", 35),
    "news.google.com": ("Google News Syndicate", 32),
    "techcrunch.com": ("TechCrunch Technology News", 30),
    "news.ycombinator.com": ("HackerNews Technology Community", 30),
}

SUSPICIOUS_TLDS = {
    ".xyz", ".top", ".click", ".win", ".buzz", ".tk", ".ml", ".ga", ".cf", ".gq",
    ".stream", ".download", ".racing", ".accountant", ".loan", ".bid",
}


class WebSearchTool(BaseTool):
  """Web search, credibility scoring, and trusted automation target selection tool."""

  name = "web_search"
  description = "Search across multi-engine cascade, evaluate trust/credibility, and pick verified automation targets."
  supported_operations = ["search", "fetch_page", "evaluate_trust", "get_trusted_target"]

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

  def evaluate_trust(self, result: Dict[str, Any], query: str = "") -> Dict[str, Any]:
    """Calculates a multi-dimensional 0-100 credibility and trust score for a search result."""
    url = result.get("url", "")
    title = result.get("title", "")
    snippet = result.get("snippet", "")
    source = result.get("source", "WebSearch")

    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
      domain = domain[4:]

    score = 40  # baseline index score
    rationales: List[str] = []

    # 1. Canonical Domain Authority
    domain_matched = False
    for t_dom, (t_name, t_pts) in TRUSTED_AUTHORITY_DOMAINS.items():
      if domain == t_dom or domain.endswith("." + t_dom):
        score += t_pts
        rationales.append(t_name)
        domain_matched = True
        break

    if not domain_matched:
      if domain.endswith(".edu"):
        score += 35
        rationales.append("Accredited Higher Education Domain (.edu)")
      elif domain.endswith(".gov"):
        score += 35
        rationales.append("Verified Government Agency (.gov)")
      elif domain.endswith(".mil"):
        score += 35
        rationales.append("Verified Official Military Domain (.mil)")
      elif domain.endswith(".org"):
        score += 20
        rationales.append("Non-Profit / Organizational Domain (.org)")
      elif any(domain.endswith(tld) for tld in SUSPICIOUS_TLDS):
        score -= 40
        rationales.append("Flagged Low-Reputation / Spam TLD")

    # Developer / Docs Subdomain bonus
    if any(parsed.netloc.startswith(prefix) for prefix in ["docs.", "api.", "developer.", "help.", "guide."]):
      score += 10
      rationales.append("Official Developer Docs Subdomain")

    # 2. Content & Keyword Alignment
    if query:
      q_terms = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 2]
      t_terms = [w.lower() for w in re.findall(r"\w+", title)]
      if q_terms:
        matches = sum(1 for qw in q_terms if qw in t_terms)
        if matches == len(q_terms):
          score += 15
          rationales.append("High Exact-Match Query Alignment")
        elif matches > 0:
          score += 8
          rationales.append("Relevant Keyword Match")

    # 3. Security & Protocol
    if url.startswith("https://"):
      score += 5
    else:
      score -= 25
      rationales.append("Insecure HTTP Protocol")

    # 4. Engine Source Grounding
    if source == "Wikipedia":
      score += 10
    elif source == "Google News":
      score += 8
    elif source == "HackerNews":
      score += 6

    final_score = max(5, min(100, score))

    if final_score >= 85:
      tier = "OFFICIAL_AUTHORITY"
      badge = "🛡️ Verified Official Authority"
    elif final_score >= 70:
      tier = "HIGH_TRUST"
      badge = "🔍 Highly Trusted Source"
    elif final_score >= 50:
      tier = "COMMUNITY_VERIFIED"
      badge = "📌 Community Verified"
    else:
      tier = "GENERAL_WEB"
      badge = "🌐 General Web Result"

    return {
        **result,
        "trust_score": final_score,
        "trust_tier": tier,
        "trust_badge": badge,
        "domain": domain,
        "is_official": final_score >= 85,
        "trust_rationale": " • ".join(rationales) if rationales else "Indexed Web Result",
    }

  def _search_wikipedia(self, query: str, max_results: int = 4) -> List[Dict[str, Any]]:
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

  def _search_google_news(self, query: str, max_results: int = 4) -> List[Dict[str, Any]]:
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

  def _search_hackernews(self, query: str, max_results: int = 3) -> List[Dict[str, Any]]:
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

  def _search_duckduckgo(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
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

  def _multi_engine_search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Cascading search across DuckDuckGo, Wikipedia, Google News, and HackerNews with Trust Scoring."""
    raw_results: List[Dict[str, Any]] = []

    # 1. Try DuckDuckGo
    ddg_res = self._search_duckduckgo(query, max_results=max_results)
    if ddg_res:
      raw_results.extend(ddg_res)

    # 2. Multi-Tier Organic Cascade
    wiki_res = self._search_wikipedia(query, max_results=max_results)
    if wiki_res:
      raw_results.extend(wiki_res)

    news_res = self._search_google_news(query, max_results=max_results)
    if news_res:
      raw_results.extend(news_res)

    if len(raw_results) < max_results:
      hn_res = self._search_hackernews(query, max_results=3)
      if hn_res:
        raw_results.extend(hn_res)

    if not raw_results:
      raw_results = [{
          "title": f"Live Web Index for '{query}'",
          "url": f"https://www.google.com/search?q={urllib.parse.quote(query)}",
          "snippet": f"Web query index searched for: {query}",
          "source": "WebSearch",
      }]

    # 3. Evaluate Trust, Filter & Rank by Authority Score
    evaluated = [self.evaluate_trust(r, query=query) for r in raw_results]
    # Sort descending by trust_score
    evaluated.sort(key=lambda x: x.get("trust_score", 0), reverse=True)

    # Deduplicate by URL
    seen_urls = set()
    deduped = []
    for r in evaluated:
      u = r.get("url")
      if u not in seen_urls:
        seen_urls.add(u)
        deduped.append(r)

    return deduped[:max_results]

  def get_trusted_automation_target(self, query: str, min_trust_score: int = 70) -> Optional[Dict[str, Any]]:
    """Picks the single highest-trust, authentic canonical URL for autonomous navigation and task execution."""
    results = self._multi_engine_search(query=query, max_results=5)
    for r in results:
      if r.get("trust_score", 0) >= min_trust_score:
        return r
    return results[0] if results else None

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

        top_trusted = [r for r in results if r.get("trust_score", 0) >= 70]

        elapsed = (time.perf_counter() - start_time) * 1000
        return ToolResult(
            action_id=action.action_id,
            tool_name=self.name,
            operation=op,
            success=True,
            data={
                "query": query,
                "results": results,
                "count": len(results),
                "top_trusted_count": len(top_trusted),
                "highest_trust_score": results[0].get("trust_score", 0) if results else 0,
            },
            execution_time_ms=elapsed,
        )

      elif op == "get_trusted_target":
        query = params.get("query") or params.get("q")
        if not query:
          raise ValueError("Parameter 'query' is required for get_trusted_target.")

        min_score = int(params.get("min_trust_score", 70))
        target = self.get_trusted_automation_target(query=query, min_trust_score=min_score)

        elapsed = (time.perf_counter() - start_time) * 1000
        return ToolResult(
            action_id=action.action_id,
            tool_name=self.name,
            operation=op,
            success=True,
            data={"query": query, "target": target},
            execution_time_ms=elapsed,
        )

      elif op == "evaluate_trust":
        url = params.get("url")
        if not url:
          raise ValueError("Parameter 'url' is required for evaluate_trust.")
        title = params.get("title", "")
        snippet = params.get("snippet", "")
        query = params.get("query", "")

        evaluation = self.evaluate_trust(
            {"url": url, "title": title, "snippet": snippet},
            query=query,
        )

        elapsed = (time.perf_counter() - start_time) * 1000
        return ToolResult(
            action_id=action.action_id,
            tool_name=self.name,
            operation=op,
            success=True,
            data=evaluation,
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
