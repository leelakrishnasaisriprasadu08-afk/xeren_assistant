"""Unit tests for the ToolRegistry and execution gateway."""

import pytest
from security.permission_gate import PermissionGate
from tools.base import Action
from tools.filesystem_tool import FilesystemTool
from tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_registry_registration_and_execution(temp_workspace):
  gate = PermissionGate(workspace_root=temp_workspace)
  registry = ToolRegistry(permission_gate=gate)
  fs_tool = FilesystemTool(workspace_root=temp_workspace, permission_gate=gate)

  registry.register_tool(fs_tool)

  # Check tool list
  tools_info = registry.list_tools()
  assert len(tools_info) == 1
  assert tools_info[0]["name"] == "filesystem"

  # Execute allowed action
  action = Action(
      action_id="act_reg_1",
      tool_name="filesystem",
      operation="read_file",
      parameters={"path": "README.md"},
  )
  result = await registry.execute_action(action)
  assert result.success is True
  assert "Xeren Workspace" in result.data["content"]


@pytest.mark.asyncio
async def test_registry_blocks_denied_operation(temp_workspace):
  gate = PermissionGate(workspace_root=temp_workspace)
  registry = ToolRegistry(permission_gate=gate)
  fs_tool = FilesystemTool(workspace_root=temp_workspace, permission_gate=gate)
  registry.register_tool(fs_tool)

  # Action trying to delete a file
  action = Action(
      action_id="act_reg_del",
      tool_name="filesystem",
      operation="delete_file",
      parameters={"path": "README.md"},
  )
  result = await registry.execute_action(action)
  assert result.success is False
  assert "Permission Denied" in result.error
