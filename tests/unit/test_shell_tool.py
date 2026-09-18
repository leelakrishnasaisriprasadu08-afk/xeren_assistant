"""Unit tests for ShellTool execution, dangerous command blocking, and timeouts."""

import pytest
from security.policies import PermissionLevel, RiskLevel
from tools.base import Action
from tools.shell_tool import ShellTool


@pytest.mark.asyncio
async def test_shell_tool_safe_execution(tmp_path):
  """Test executing a safe command inside the workspace sandbox."""
  tool = ShellTool(workspace_root=tmp_path)
  action = Action(
      action_id="sh_01",
      tool_name="shell",
      operation="execute_command",
      parameters={"command": "python -c \"print('Xeren Shell OK')\""},
      required_permission=PermissionLevel.ASK,
      risk_level=RiskLevel.HIGH,
      reason="Test shell",
  )

  res = await tool.execute(action)
  assert res.success is True
  assert res.data["exit_code"] == 0
  assert "Xeren Shell OK" in res.data["stdout"]


@pytest.mark.asyncio
async def test_shell_tool_blocks_dangerous_commands(tmp_path):
  """Test that destructive commands are intercepted and blocked before execution."""
  tool = ShellTool(workspace_root=tmp_path)

  dangerous_commands = [
      "rm -rf /",
      "mkfs.ext4 /dev/sda1",
      "format C:",
      "del /s C:\\Windows",
      "diskpart",
  ]

  for cmd in dangerous_commands:
    action = Action(
        action_id="sh_bad",
        tool_name="shell",
        operation="execute_command",
        parameters={"command": cmd},
        required_permission=PermissionLevel.ASK,
        risk_level=RiskLevel.HIGH,
        reason="Malicious attempt",
    )
    res = await tool.execute(action)
    assert res.success is False
    assert "blocked by security policy" in res.error.lower()


@pytest.mark.asyncio
async def test_shell_tool_timeout(tmp_path):
  """Test that long-running commands are terminated after the timeout threshold."""
  tool = ShellTool(workspace_root=tmp_path)
  action = Action(
      action_id="sh_timeout",
      tool_name="shell",
      operation="execute_command",
      parameters={
          "command": "python -c \"import time; time.sleep(5)\"",
          "timeout": 0.5,
      },
      required_permission=PermissionLevel.ASK,
      risk_level=RiskLevel.HIGH,
      reason="Test timeout",
  )

  res = await tool.execute(action)
  assert res.success is False
  assert "timed out" in res.error.lower()
