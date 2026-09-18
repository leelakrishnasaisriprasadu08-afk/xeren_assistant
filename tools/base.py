"""Base Tool abstractions and Action schemas."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from security.policies import PermissionLevel, RiskLevel
from security.trust_boundary import UntrustedData


class Action(BaseModel):
  """Strict Action schema between Planner and Controller."""

  action_id: str = Field(
      description="Unique identifier for the action (e.g. 'act_001')"
  )
  tool_name: str = Field(
      description="Registered tool name (e.g. 'filesystem', 'github')"
  )
  operation: str = Field(
      description="Specific operation (e.g. 'read_file', 'read_issues')"
  )
  parameters: Dict[str, Any] = Field(
      default_factory=dict, description="Validated tool arguments"
  )
  required_permission: PermissionLevel = Field(
      default=PermissionLevel.ALLOWED,
      description="Required permission level for this operation",
  )
  risk_level: RiskLevel = Field(
      default=RiskLevel.LOW,
      description="Risk classification for this operation",
  )
  reason: str = Field(
      default="",
      description="Planner explanation for why this action is necessary",
  )
  timeout: float = Field(
      default=10.0, description="Per-action timeout limit in seconds"
  )


class ToolResult(BaseModel):
  """Structured result returned by a tool execution."""

  action_id: str
  tool_name: str
  operation: str
  success: bool
  data: Any = None
  error: Optional[str] = None
  execution_time_ms: float = 0.0
  untrusted_payload: Optional[UntrustedData] = None


class BaseTool(ABC):
  """Abstract base class for all Xeren Assistant tools."""

  name: str
  description: str
  supported_operations: List[str]

  @abstractmethod
  async def execute(self, action: Action) -> ToolResult:
    """Executes the given validated action and returns a structured ToolResult."""
    pass
