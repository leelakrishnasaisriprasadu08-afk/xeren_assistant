"""Subagent Delegation Tool exposing specialized autonomous agents to the Planner and Controller."""

import time
from typing import Any, Dict, List, Optional
from agents.base import BaseSubagent, SubagentResult
from agents.researcher import ResearchSubagent
from agents.reviewer import CodeReviewerSubagent
from models.base import BaseLLMProvider
from .base import Action, BaseTool, ToolResult
from .registry import ToolRegistry


class SubagentTool(BaseTool):
  """Exposes specialized subagent execution to the Task Planner and Controller."""

  name = "subagent"
  description = "Delegates complex sub-tasks to specialized autonomous subagents (researcher, code_reviewer)."
  supported_operations: List[str] = [
      "delegate_research",
      "delegate_code_review",
  ]

  def __init__(
      self,
      llm_provider: BaseLLMProvider,
      tool_registry: Optional[ToolRegistry] = None,
  ):
    self.llm_provider = llm_provider
    self.tool_registry = tool_registry
    self.researcher = ResearchSubagent(
        llm_provider=llm_provider, tool_registry=tool_registry
    )
    self.reviewer = CodeReviewerSubagent(
        llm_provider=llm_provider, tool_registry=tool_registry
    )

  async def execute(self, action: Action) -> ToolResult:
    start_time = time.perf_counter()
    op = action.operation.lower()
    params = action.parameters

    goal = params.get("goal") or params.get("task") or action.reason or "Execute subagent task"

    if op == "delegate_research":
      res = await self.researcher.run(goal=goal, context=params)
      elapsed = (time.perf_counter() - start_time) * 1000
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=res.success,
          data=res.model_dump(),
          error=res.error,
          execution_time_ms=elapsed,
      )

    elif op == "delegate_code_review":
      res = await self.reviewer.run(goal=goal, context=params)
      elapsed = (time.perf_counter() - start_time) * 1000
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=res.success,
          data=res.model_dump(),
          error=res.error,
          execution_time_ms=elapsed,
      )

    else:
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=False,
          error=f"Unsupported subagent operation: {action.operation}",
      )
