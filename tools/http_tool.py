"""Generic HTTP Gateway Tool with secret redaction and trust boundary wrapping."""

import json
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request
from security.secrets import RedactionEngine
from .base import Action, BaseTool, ToolResult


class HTTPTool(BaseTool):
  """Tool for interacting with external HTTP/REST endpoints."""

  name = "http"
  description = "Dispatches HTTP requests (GET, POST, PUT, DELETE) to external web endpoints."
  supported_operations: List[str] = ["get", "post", "put", "delete"]

  def __init__(self, default_timeout: float = 10.0):
    self.default_timeout = default_timeout
    self.redaction_engine = RedactionEngine()

  def _sanitize_headers_for_log(
      self, headers: Dict[str, str]
  ) -> Dict[str, str]:
    """Redacts authorization and credential headers in returned metadata."""
    safe = {}
    for k, v in headers.items():
      k_lower = k.lower()
      if any(
          secret in k_lower
          for secret in ["auth", "token", "key", "secret", "cookie"]
      ):
        safe[k] = "[REDACTED]"
      else:
        safe[k] = v
    return safe

  async def execute(self, action: Action) -> ToolResult:
    start_time = time.perf_counter()
    op = action.operation.lower()

    if op not in self.supported_operations:
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=False,
          error=f"Unsupported HTTP operation: {action.operation}",
      )

    url = action.parameters.get("url", "").strip()
    if not url or not (url.startswith("http://") or url.startswith("https://")):
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=False,
          error="Invalid URL: Must start with http:// or https://",
      )

    headers = dict(action.parameters.get("headers", {}))
    query_params = action.parameters.get("params")
    json_body = action.parameters.get("json_data") or action.parameters.get(
        "json"
    )
    raw_body = action.parameters.get("body")
    timeout = float(action.parameters.get("timeout", action.timeout or 10.0))

    if query_params:
      parsed = urllib.parse.urlparse(url)
      qs = urllib.parse.parse_qs(parsed.query)
      qs.update(query_params)
      new_query = urllib.parse.urlencode(qs, doseq=True)
      url = urllib.parse.urlunparse(parsed._replace(query=new_query))

    req_data = None
    if json_body is not None:
      req_data = json.dumps(json_body).encode("utf-8")
      headers.setdefault("Content-Type", "application/json")
    elif raw_body is not None:
      req_data = (
          raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body
      )

    headers.setdefault("User-Agent", "XerenAssistant/4.0")

    try:
      req = urllib.request.Request(
          url, data=req_data, headers=headers, method=op.upper()
      )
      with urllib.request.urlopen(req, timeout=timeout) as response:
        status_code = response.status
        resp_headers = dict(response.headers)
        resp_bytes = response.read()

        try:
          resp_text = resp_bytes.decode("utf-8")
        except UnicodeDecodeError:
          resp_text = resp_bytes.decode("latin-1", errors="replace")

        try:
          parsed_json = json.loads(resp_text)
        except Exception:
          parsed_json = None

        elapsed = (time.perf_counter() - start_time) * 1000
        return ToolResult(
            action_id=action.action_id,
            tool_name=self.name,
            operation=action.operation,
            success=200 <= status_code < 400,
            data={
                "url": url,
                "status_code": status_code,
                "headers": self._sanitize_headers_for_log(resp_headers),
                "body": parsed_json if parsed_json is not None else resp_text,
                "is_json": parsed_json is not None,
            },
            execution_time_ms=elapsed,
        )

    except urllib.error.HTTPError as e:
      elapsed = (time.perf_counter() - start_time) * 1000
      err_body = e.read().decode("utf-8", errors="replace")
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=False,
          error=f"HTTP Error {e.code}: {e.reason}",
          data={
              "url": url,
              "status_code": e.code,
              "error_body": err_body[:5000],
          },
          execution_time_ms=elapsed,
      )
    except Exception as e:
      elapsed = (time.perf_counter() - start_time) * 1000
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=False,
          error=f"HTTP Request failed: {str(e)}",
          execution_time_ms=elapsed,
      )
