"""Tool Registry and Execution Gateway."""

import asyncio
from typing import Any, Dict, List, Optional
from config.settings import Settings, get_settings
from security.permission_gate import (
    PathContainmentError,
    PermissionDeniedError,
    PermissionGate,
)
from security.policies import OperationPolicy, PermissionLevel, RiskLevel, get_operation_policy
from security.trust_boundary import TrustBoundary
from .base import Action, BaseTool, ToolResult
from .browser_tool import BrowserTool
from .codebase_tool import CodebaseTool
from .communication_tool import CommunicationTool
from .device_tool import DeviceTool
from .filesystem_tool import FilesystemTool
from .github_tool import GitHubTool
from .http_tool import HTTPTool
from .patch_tool import PatchTool
from .shell_tool import ShellTool
from .task_tool import TaskTool
from .vault_tool import VaultTool
from .vision_tool import VisionTool
from .voice_tool import VoiceTool
from .web_builder_tool import WebBuilderTool
from .web_search_tool import WebSearchTool


class ToolRegistry:
  """Central registry and execution gateway for all tools in Xeren Assistant."""

  def __init__(
      self,
      permission_gate: Optional[PermissionGate] = None,
      trust_boundary: Optional[TrustBoundary] = None,
  ):
    self.permission_gate = permission_gate or PermissionGate()
    self.trust_boundary = trust_boundary or TrustBoundary()
    self._tools: Dict[str, BaseTool] = {}

  def register_tool(self, tool: BaseTool) -> None:
    """Registers a tool instance in the registry."""
    self._tools[tool.name.lower()] = tool

  def get_tool(self, name: str) -> Optional[BaseTool]:
    """Retrieves a registered tool by name."""
    return self._tools.get(name.lower())

  def list_tools(self) -> List[Dict[str, Any]]:
    """Returns a list of metadata for all registered tools and operations."""
    summary = []
    for tool in self._tools.values():
      ops_info = []
      for op in tool.supported_operations:
        policy = get_operation_policy(tool.name, op)
        ops_info.append({
            "operation": op,
            "permission_level": policy.permission_level.value,
            "risk_level": policy.risk_level.value,
            "description": policy.description,
        })
      summary.append({
          "name": tool.name,
          "description": tool.description,
          "operations": ops_info,
      })
    return summary

  async def execute_action(self, action: Action) -> ToolResult:
    """Safely executes an action through Permission Gate and Tool Registry.

    Enforces permission validation, per-action timeout, and trust boundary
    wrapping.
    """
    # 1. Evaluate Permission Gate first (Enforces ALLOWED / ASK / DENIED policies)
    try:
      await self.permission_gate.evaluate_permission_async(
          tool_name=action.tool_name,
          operation=action.operation,
          parameters=action.parameters,
      )
    except PermissionDeniedError as e:
      return ToolResult(
          action_id=action.action_id,
          tool_name=action.tool_name,
          operation=action.operation,
          success=False,
          error=f"Permission Denied: {str(e)}",
      )

    # 2. Lookup registered tool
    tool_name = action.tool_name.lower()
    tool = self.get_tool(tool_name)
    if not tool:
      return ToolResult(
          action_id=action.action_id,
          tool_name=action.tool_name,
          operation=action.operation,
          success=False,
          error=(
              f"Tool '{action.tool_name}' is not registered in Tool Registry."
          ),
      )

    if action.operation.lower() not in [
        op.lower() for op in tool.supported_operations
    ]:
      return ToolResult(
          action_id=action.action_id,
          tool_name=action.tool_name,
          operation=action.operation,
          success=False,
          error=(
              f"Operation '{action.operation}' is not supported by tool"
              f" '{tool.name}'."
          ),
      )

    # 2. Execute with bounded timeout
    try:
      timeout_secs = action.timeout if action.timeout > 0 else 10.0
      result = await asyncio.wait_for(tool.execute(action), timeout=timeout_secs)
    except asyncio.TimeoutError:
      return ToolResult(
          action_id=action.action_id,
          tool_name=action.tool_name,
          operation=action.operation,
          success=False,
          error=(
              f"Action '{action.action_id}' timed out after {timeout_secs}s."
          ),
      )
    except Exception as e:
      return ToolResult(
          action_id=action.action_id,
          tool_name=action.tool_name,
          operation=action.operation,
          success=False,
          error=f"Execution error: {str(e)}",
      )

    # 3. Apply Trust Boundary if external source
    if tool_name in ["github", "web_search"] and result.success and result.data:
      result.untrusted_payload = self.trust_boundary.wrap_external_data(
          source=f"{tool_name}:{action.operation}", content=result.data
      )

    return result


def get_default_registry(settings: Optional[Settings] = None) -> ToolRegistry:
  """Factory creating a fully initialized default ToolRegistry."""
  current_settings = settings or get_settings()
  gate = PermissionGate(workspace_root=current_settings.workspace_root)
  trust_bound = TrustBoundary()

  registry = ToolRegistry(permission_gate=gate, trust_boundary=trust_bound)

  # Register core Phase-1 tools
  registry.register_tool(
      FilesystemTool(
          workspace_root=current_settings.workspace_root, permission_gate=gate
      )
  )
  registry.register_tool(GitHubTool())
  registry.register_tool(WebSearchTool())
  registry.register_tool(TaskTool(db_path=current_settings.db_path))
  registry.register_tool(
      ShellTool(workspace_root=current_settings.workspace_root)
  )
  registry.register_tool(HTTPTool())
  registry.register_tool(CodebaseTool())
  registry.register_tool(PatchTool())
  registry.register_tool(DeviceTool())
  registry.register_tool(BrowserTool())
  registry.register_tool(VisionTool())
  registry.register_tool(CommunicationTool(client_store=None))
  registry.register_tool(VaultTool())
  registry.register_tool(VoiceTool())
  registry.register_tool(WebBuilderTool())

  return registry
