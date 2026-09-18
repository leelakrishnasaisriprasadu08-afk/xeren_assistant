import os
import time
from typing import Any, Dict, List, Optional
import requests
from config.settings import get_settings
from security.secrets import SecretStore
from .base import Action, BaseTool, ToolResult


class GitHubTool(BaseTool):
  """GitHub integration tool supporting reads and authorized writes."""

  name = "github"
  description = "Read GitHub repositories, issues, PRs, and create authorized issues or pull requests."
  supported_operations = [
      "get_repo",
      "read_issues",
      "read_prs",
      "get_commits",
      "create_issue",
      "create_pr",
  ]

  def __init__(
      self,
      secret_store: Optional[SecretStore] = None,
      session: Optional[requests.Session] = None,
  ):
    self.secret_store = secret_store or SecretStore.get_instance()
    self.session = session or requests.Session()

  def _get_headers(self) -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Xeren-Assistant/0.2.0",
    }
    settings = get_settings()
    token = (
        self.secret_store.get_secret("GITHUB_TOKEN")
        or getattr(settings, "github_token", None)
        or os.environ.get("GITHUB_TOKEN")
    )
    if token:
      headers["Authorization"] = f"Bearer {token}"
    return headers

  def _parse_repo(self, params: Dict[str, Any]) -> tuple[str, str]:
    full_name = params.get("repo") or params.get("repository") or ""
    if "/" in full_name:
      owner, repo = full_name.split("/", 1)
      return owner.strip(), repo.strip()

    owner = params.get("owner", "").strip()
    repo = params.get("repo_name", "").strip()
    if not owner or not repo:
      raise ValueError(
          "GitHub repository must be specified as 'owner/repo' or via 'owner'"
          " and 'repo' parameters."
      )
    return owner, repo

  async def execute(self, action: Action) -> ToolResult:
    start_time = time.perf_counter()
    op = action.operation.lower()
    params = action.parameters or {}
    headers = self._get_headers()

    try:
      owner, repo = self._parse_repo(params)
      base_url = f"https://api.github.com/repos/{owner}/{repo}"

      if op == "get_repo":
        resp = self.session.get(base_url, headers=headers, timeout=10)
        resp.raise_for_status()
        raw = resp.json()
        data = {
            "full_name": raw.get("full_name"),
            "description": raw.get("description"),
            "stars": raw.get("stargazers_count"),
            "forks": raw.get("forks_count"),
            "open_issues_count": raw.get("open_issues_count"),
            "default_branch": raw.get("default_branch"),
            "language": raw.get("language"),
        }

      elif op == "read_issues":
        state = params.get("state", "open")
        limit = min(int(params.get("limit", 10)), 50)
        url = f"{base_url}/issues?state={state}&per_page={limit}"
        resp = self.session.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        raw_list = resp.json()
        data = [
            {
                "number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "user": item.get("user", {}).get("login"),
                "comments": item.get("comments"),
                "created_at": item.get("created_at"),
                "body_snippet": (
                    item.get("body", "")[:300] if item.get("body") else ""
                ),
            }
            for item in raw_list
            if "pull_request" not in item
        ]

      elif op == "read_prs":
        state = params.get("state", "open")
        limit = min(int(params.get("limit", 10)), 50)
        url = f"{base_url}/pulls?state={state}&per_page={limit}"
        resp = self.session.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        raw_list = resp.json()
        data = [
            {
                "number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "user": item.get("user", {}).get("login"),
                "created_at": item.get("created_at"),
                "head": item.get("head", {}).get("ref"),
                "base": item.get("base", {}).get("ref"),
            }
            for item in raw_list
        ]

      elif op == "get_commits":
        limit = min(int(params.get("limit", 10)), 50)
        url = f"{base_url}/commits?per_page={limit}"
        resp = self.session.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        raw_list = resp.json()
        data = [
            {
                "sha": item.get("sha")[:7],
                "author": item.get("commit", {})
                .get("author", {})
                .get("name"),
                "date": item.get("commit", {}).get("author", {}).get("date"),
                "message": item.get("commit", {}).get("message"),
            }
            for item in raw_list
        ]

      elif op == "create_issue":
        title = params.get("title")
        if not title:
          raise ValueError("Parameter 'title' is required for create_issue.")

        body = params.get("body", "")
        labels = params.get("labels", [])
        payload = {"title": title, "body": body, "labels": labels}

        resp = self.session.post(
            f"{base_url}/issues", json=payload, headers=headers, timeout=10
        )
        resp.raise_for_status()
        raw = resp.json()
        data = {
            "issue_number": raw.get("number"),
            "html_url": raw.get("html_url"),
            "title": raw.get("title"),
            "state": raw.get("state"),
        }

      elif op == "create_pr":
        title = params.get("title")
        head = params.get("head")
        base = params.get("base", "main")
        if not title or not head:
          raise ValueError(
              "Parameters 'title' and 'head' are required for create_pr."
          )

        body = params.get("body", "")
        payload = {
            "title": title,
            "head": head,
            "base": base,
            "body": body,
            "draft": bool(params.get("draft", False)),
        }

        resp = self.session.post(
            f"{base_url}/pulls", json=payload, headers=headers, timeout=10
        )
        resp.raise_for_status()
        raw = resp.json()
        data = {
            "pr_number": raw.get("number"),
            "html_url": raw.get("html_url"),
            "title": raw.get("title"),
            "head": head,
            "base": base,
            "state": raw.get("state"),
        }

      else:
        raise ValueError(
            f"Unsupported operation '{op}' for tool '{self.name}'"
        )

      elapsed = (time.perf_counter() - start_time) * 1000
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=op,
          success=True,
          data=data,
          execution_time_ms=elapsed,
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
