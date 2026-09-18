"""Base abstractions for specialized autonomous subagents."""

from abc import ABC, abstractmethod
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from models.base import BaseLLMProvider, LLMMessage, LLMResponse
from security.trust_boundary import UntrustedData
from tools.base import Action, ToolResult
from tools.registry import ToolRegistry


class SubagentResult(BaseModel):
  """Structured outcome of a specialized subagent execution."""

  subagent_name: str
  goal: str
  success: bool
  findings: str
  structured_data: Dict[str, Any] = Field(default_factory=dict)
  actions_executed: List[Dict[str, Any]] = Field(default_factory=list)
  duration_ms: float = 0.0
  error: Optional[str] = None
  untrusted_payload: Optional[UntrustedData] = None


class BaseSubagent(ABC):
  """Abstract base class for specialized domain subagents."""

  name: str
  role_description: str
  allowed_tools: List[str]

  def __init__(
      self,
      llm_provider: BaseLLMProvider,
      tool_registry: Optional[ToolRegistry] = None,
  ):
    self.llm_provider = llm_provider
    self.tool_registry = tool_registry

  @abstractmethod
  async def run(self, goal: str, context: Optional[Dict[str, Any]] = None) -> SubagentResult:
    """Executes the subagent toward the specified goal and returns structured findings."""
    pass
