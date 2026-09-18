"""Security tests for Phase 2 interactive approvals and diff previews."""

import pytest
from security.permission_gate import (
    ApprovalRequest,
    PermissionDeniedError,
    PermissionGate,
)
from tools.base import Action
from tools.filesystem_tool import FilesystemTool
from tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_write_operation_triggers_approval_with_diff(temp_workspace):
  received_requests = []

  def mock_approval_callback(req: ApprovalRequest) -> bool:
    received_requests.append(req)
    # Approve write
    return True

  gate = PermissionGate(
      workspace_root=temp_workspace, approval_callback=mock_approval_callback
  )
  registry = ToolRegistry(permission_gate=gate)
  fs_tool = FilesystemTool(workspace_root=temp_workspace, permission_gate=gate)
  registry.register_tool(fs_tool)

  # Write action
  action = Action(
      action_id="act_w1",
      tool_name="filesystem",
      operation="write_file",
      parameters={"path": "new_code.py", "content": "print('phase 2 works')\n"},
  )
  result = await registry.execute_action(action)

  assert result.success is True
  assert len(received_requests) == 1
  req = received_requests[0]
  assert req.tool_name == "filesystem"
  assert req.operation == "write_file"
  assert req.diff_preview is not None


@pytest.mark.asyncio
async def test_rejected_approval_halts_safely(temp_workspace):
  def rejecting_callback(req: ApprovalRequest) -> bool:
    return False

  gate = PermissionGate(
      workspace_root=temp_workspace, approval_callback=rejecting_callback
  )
  registry = ToolRegistry(permission_gate=gate)
  fs_tool = FilesystemTool(workspace_root=temp_workspace, permission_gate=gate)
  registry.register_tool(fs_tool)

  action = Action(
      action_id="act_w2",
      tool_name="filesystem",
      operation="write_file",
      parameters={"path": "blocked.py", "content": "malicious payload"},
  )
  result = await registry.execute_action(action)

  assert result.success is False
  assert "Permission Denied" in result.error
  # Verify file was never written to disk
  assert not (temp_workspace / "blocked.py").exists()
