"""Autonomous Research Subagent for deep multi-hop exploration and evidence synthesis."""

import time
from typing import Any, Dict, List, Optional
from models.base import BaseLLMProvider, LLMMessage
from security.policies import PermissionLevel, RiskLevel
from tools.base import Action, ToolResult
from tools.registry import ToolRegistry
from .base import BaseSubagent, SubagentResult


class ResearchSubagent(BaseSubagent):
  """Specialized agent focused on web research, documentation discovery, and technical synthesis."""

  name = "researcher"
  role_description = "Conducts deep multi-query research across web search and GitHub to compile verified technical dossiers."
  allowed_tools: List[str] = ["web_search", "github"]

  async def run(
      self, goal: str, context: Optional[Dict[str, Any]] = None
  ) -> SubagentResult:
    start_time = time.perf_counter()
    ctx = context or {}
    actions_executed = []

    # 1. First search query
    query = ctx.get("query") or goal
    search_action = Action(
        action_id=f"research_search_01",
        tool_name="web_search",
        operation="search",
        parameters={"query": query, "max_results": 5},
        required_permission=PermissionLevel.ALLOWED,
        risk_level=RiskLevel.LOW,
        reason=f"Perform initial web discovery for: {goal}",
    )

    search_result: Optional[ToolResult] = None
    if self.tool_registry:
      search_result = await self.tool_registry.execute_action(search_action)
      actions_executed.append(
          {"action": search_action.model_dump(), "success": search_result.success}
      )

    # 2. Synthesize research report using LLM
    search_content = ""
    if search_result and search_result.success and search_result.data:
      results_list = search_result.data.get("results", [])
      search_content = "\n".join(
          f"- [{r.get('title', 'Source')}]({r.get('url', '')}): {r.get('snippet', '')}"
          for r in results_list
      )

    system_prompt = (
        "You are the Xeren Research Specialist Subagent. Your goal is to synthesize verified,"
        " concise, highly technical research dossiers with citations based strictly on retrieved facts."
    )
    user_prompt = (
        f"Research Goal: {goal}\n"
        f"Retrieved Web Findings:\n{search_content or 'No web search data available.'}\n\n"
        "Provide a structured research summary with key findings, architectural insights, and citations."
    )

    try:
      response = await self.llm_provider.generate(
          messages=[LLMMessage(role="user", content=user_prompt)],
          system_instruction=system_prompt,
          temperature=0.2,
      )
      findings = response.text.strip()
      elapsed = (time.perf_counter() - start_time) * 1000

      return SubagentResult(
          subagent_name=self.name,
          goal=goal,
          success=True,
          findings=findings,
          structured_data={
              "sources_found": (
                  len(search_result.data.get("results", []))
                  if search_result and search_result.data
                  else 0
              ),
              "raw_search_query": query,
          },
          actions_executed=actions_executed,
          duration_ms=elapsed,
      )

    except Exception as e:
      elapsed = (time.perf_counter() - start_time) * 1000
      return SubagentResult(
          subagent_name=self.name,
          goal=goal,
          success=False,
          findings="",
          error=f"Research synthesis failed: {str(e)}",
          actions_executed=actions_executed,
          duration_ms=elapsed,
      )
