"""Unit tests for DynamicReplanner self-healing heuristics and fallback."""

import pytest
from core.dag import DAGAction
from core.replanner import DynamicReplanner
from models.base import BaseLLMProvider, LLMResponse
from security.policies import PermissionLevel, RiskLevel
from tools.base import Action, ToolResult


class MockReplannerLLM(BaseLLMProvider):
  async def generate(self, messages, system_instruction=None, temperature=0.0):
    return LLMResponse(
        text='```json\n{"action_id": "llm_repair_1", "tool_name": "filesystem", "operation": "list_dir", "parameters": {"path": "."}, "reason": "Recover by listing current directory"}\n```',
        model_name="mock-llm",
    )


def test_replanner_file_not_found_recovery():
  """Test that a file not found error deterministically yields a workspace search action."""
  replanner = DynamicReplanner()
  failed_action = Action(
      action_id="read_missing",
      tool_name="filesystem",
      operation="read_file",
      parameters={"path": "unknown/config.json"},
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="Read configuration file",
  )

  repair = replanner.plan_correction_deterministic(
      failed_action=failed_action,
      error_message="File 'unknown/config.json' not found in workspace",
      user_query="Find my config",
  )

  assert repair is not None
  assert repair.tool_name == "filesystem"
  assert repair.operation == "search_files"
  assert repair.parameters["query"] == "config"
  assert "read_missing_repair" == repair.action_id


def test_replanner_web_search_broadening():
  """Test that empty or failed web search yields a broader query repair."""
  replanner = DynamicReplanner()
  failed_action = Action(
      action_id="search_complex",
      tool_name="web_search",
      operation="search",
      parameters={"query": "hyper-specific obscure react hook syntax error 2026"},
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="Search web for obscure issue",
  )

  repair = replanner.plan_correction_deterministic(
      failed_action=failed_action,
      error_message="No results returned",
      user_query="Search web",
  )

  assert repair is not None
  assert repair.tool_name == "web_search"
  assert repair.operation == "search"
  assert len(repair.parameters["query"].split()) <= 3


def test_replanner_github_fallback_to_web():
  """Test that inaccessible github repo produces a web search fallback."""
  replanner = DynamicReplanner()
  failed_action = Action(
      action_id="gh_fetch",
      tool_name="github",
      operation="get_repo",
      parameters={"repo": "nonexistent/repo123"},
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="Fetch repo stats",
  )

  repair = replanner.plan_correction_deterministic(
      failed_action=failed_action,
      error_message="Repository nonexistent/repo123 not found (404)",
      user_query="Check repo nonexistent/repo123",
  )

  assert repair is not None
  assert repair.tool_name == "web_search"
  assert repair.operation == "search"
  assert "nonexistent/repo123" in repair.parameters["query"]


@pytest.mark.asyncio
async def test_replanner_llm_fallback():
  """Test that unknown error patterns fall back to LLM-assisted repair planning."""
  replanner = DynamicReplanner(llm_provider=MockReplannerLLM())
  failed_action = Action(
      action_id="custom_fail",
      tool_name="tasks",
      operation="custom_op",
      parameters={},
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="Custom op",
  )

  repair = await replanner.plan_correction(
      failed_action=failed_action,
      error_message="Unexpected unknown internal error 500",
      user_query="Perform task",
      prior_results={},
  )

  assert repair is not None
  assert repair.action_id == "llm_repair_1"
  assert repair.tool_name == "filesystem"
  assert repair.operation == "list_dir"
