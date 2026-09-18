"""Unit tests for HTTPTool generic REST client and secret header sanitization."""

import pytest
from security.policies import PermissionLevel, RiskLevel
from tools.base import Action
from tools.http_tool import HTTPTool


@pytest.mark.asyncio
async def test_http_tool_header_sanitization():
  """Test that secret headers (Authorization, Tokens, Keys) are redacted in result logs."""
  tool = HTTPTool()
  raw_headers = {
      "Authorization": "Bearer super-secret-jwt-token-12345",
      "X-API-Key": "secret-api-key-999",
      "Content-Type": "application/json",
      "Accept": "text/html",
  }

  sanitized = tool._sanitize_headers_for_log(raw_headers)
  assert sanitized["Authorization"] == "[REDACTED]"
  assert sanitized["X-API-Key"] == "[REDACTED]"
  assert sanitized["Content-Type"] == "application/json"
  assert sanitized["Accept"] == "text/html"


@pytest.mark.asyncio
async def test_http_tool_invalid_url():
  """Test that invalid URL schemes are rejected."""
  tool = HTTPTool()
  action = Action(
      action_id="http_01",
      tool_name="http",
      operation="get",
      parameters={"url": "ftp://malicious-ftp-server/data"},
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="Test invalid url",
  )

  res = await tool.execute(action)
  assert res.success is False
  assert "Invalid URL" in res.error
