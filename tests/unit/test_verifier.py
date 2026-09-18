"""Unit tests for deterministic Verifier."""

from core.verifier import Verifier
from tools.base import Action, ToolResult


def test_verifier_passes_valid_file_result():
  verifier = Verifier()
  action = Action(
      action_id="act_01",
      tool_name="filesystem",
      operation="read_file",
      parameters={"path": "README.md"},
  )
  result = ToolResult(
      action_id="act_01",
      tool_name="filesystem",
      operation="read_file",
      success=True,
      data={"path": "README.md", "content": "Sample content"},
  )
  v_res = verifier.verify_action_result(action, result)
  assert v_res.verified is True


def test_verifier_fails_on_tool_failure():
  verifier = Verifier()
  action = Action(
      action_id="act_01",
      tool_name="filesystem",
      operation="read_file",
      parameters={"path": "invalid.txt"},
  )
  result = ToolResult(
      action_id="act_01",
      tool_name="filesystem",
      operation="read_file",
      success=False,
      error="File not found",
  )
  v_res = verifier.verify_action_result(action, result)
  assert v_res.verified is False
  assert v_res.is_retryable is True
