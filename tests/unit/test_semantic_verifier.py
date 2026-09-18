"""Unit tests for Dual-Loop Verifier (Deterministic structural + Semantic response checks)."""

import pytest
from core.verifier import Verifier
from security.policies import PermissionLevel, RiskLevel
from tools.base import Action, ToolResult


def test_verifier_loop1_deterministic_filesystem():
  """Test Loop 1 structural verification on file system operations."""
  verifier = Verifier()

  # 1. Valid file read
  act_read = Action(
      action_id="a1",
      tool_name="filesystem",
      operation="read_file",
      parameters={"path": "test.txt"},
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="Read file",
  )
  res_valid = ToolResult(
      action_id="a1",
      tool_name="filesystem",
      operation="read_file",
      success=True,
      data={"path": "test.txt", "content": "hello world"},
  )
  v_res = verifier.verify_action_result(act_read, res_valid)
  assert v_res.verified is True

  # 2. Invalid file read missing 'content' key
  res_invalid = ToolResult(
      action_id="a1",
      tool_name="filesystem",
      operation="read_file",
      success=True,
      data={"path": "test.txt"},  # missing content
  )
  v_res_inv = verifier.verify_action_result(act_read, res_invalid)
  assert v_res_inv.verified is False
  assert "Invalid file read response structure" in v_res_inv.feedback


def test_verifier_loop1_deterministic_tasks():
  """Test Loop 1 structural verification on task management operations."""
  verifier = Verifier()

  act_task = Action(
      action_id="t1",
      tool_name="tasks",
      operation="create_task",
      parameters={"title": "New Task"},
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="Create task",
  )
  res_valid = ToolResult(
      action_id="t1",
      tool_name="tasks",
      operation="create_task",
      success=True,
      data={"task_id": "tsk-123", "title": "New Task"},
  )
  assert verifier.verify_action_result(act_task, res_valid).verified is True

  res_missing_id = ToolResult(
      action_id="t1",
      tool_name="tasks",
      operation="create_task",
      success=True,
      data={"title": "New Task"},
  )
  v_res = verifier.verify_action_result(act_task, res_missing_id)
  assert v_res.verified is False
  assert "failed to return a valid task_id" in v_res.feedback


@pytest.mark.asyncio
async def test_verifier_loop2_semantic_checks():
  """Test Loop 2 semantic checks for empty outputs, broken markdown links, and failure contradictions."""
  verifier = Verifier()

  # 1. Empty response check
  v1 = await verifier.verify_semantic_response("Hello", "", {})
  assert v1.verified is False
  assert "empty" in v1.feedback.lower()

  # 2. Broken markdown links check
  v2 = await verifier.verify_semantic_response(
      "Search for docs", "Here is the doc: [FastAPI]()", {}
  )
  assert v2.verified is False
  assert "broken/empty markdown links" in v2.feedback

  # 3. Contradictory failure claim when tools succeeded
  tool_results = {
      "act_1": ToolResult(
          action_id="act_1",
          tool_name="filesystem",
          operation="read_file",
          success=True,
          data={"content": "data"},
      )
  }
  v3 = await verifier.verify_semantic_response(
      "Read my file",
      "I attempted to read the file, but execution failed.",
      tool_results,
  )
  assert v3.verified is False
  assert "incorrectly claims failure" in v3.feedback

  # 4. Valid response
  v4 = await verifier.verify_semantic_response(
      "Read my file",
      "Here is the content of your file: data",
      tool_results,
  )
  assert v4.verified is True
  assert v4.anti_hallucination_passed is True
