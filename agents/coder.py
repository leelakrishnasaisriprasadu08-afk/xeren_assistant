"""Autonomous Coder Subagent for code generation, patching, and technical implementations."""

import time
from typing import Any, Dict, List, Optional
from models.base import BaseLLMProvider, LLMMessage
from tools.registry import ToolRegistry
from .base import BaseSubagent, SubagentResult


class CoderSubagent(BaseSubagent):
  """Specialized agent focused on software development, algorithmic implementation, and refactoring."""

  name = "coder"
  role_description = "Generates high-performance, secure, and production-grade code solutions, patches, and implementations."
  allowed_tools: List[str] = ["filesystem", "tasks"]

  async def run(
      self, goal: str, context: Optional[Dict[str, Any]] = None
  ) -> SubagentResult:
    start_time = time.perf_counter()
    ctx = context or {}

    research_context = ctx.get("research_dossier", "")
    review_feedback = ctx.get("review_feedback", "")
    existing_code = ctx.get("existing_code", "")

    system_prompt = (
        "You are the Xeren Senior Software Engineer and Polyglot Developer. "
        "Generate clean, robust, highly maintainable code with full type annotations, "
        "docstrings, and comprehensive error handling. Avoid placeholder code."
    )

    user_prompt = (
        f"Coding Task Goal: {goal}\n\n"
        f"Technical Context / Research:\n{research_context or 'None provided.'}\n\n"
        f"Existing Code:\n{existing_code or 'None'}\n\n"
        f"Reviewer Feedback to Fix:\n{review_feedback or 'None'}\n\n"
        "Provide a complete, production-ready implementation with explanations."
    )

    try:
      response = await self.llm_provider.generate(
          messages=[LLMMessage(role="user", content=user_prompt)],
          system_instruction=system_prompt,
          temperature=0.1,
      )
      code_solution = response.text.strip()
      elapsed = (time.perf_counter() - start_time) * 1000

      return SubagentResult(
          subagent_name=self.name,
          goal=goal,
          success=True,
          findings=code_solution,
          structured_data={
              "has_code_blocks": "```" in code_solution,
              "has_fixed_feedback": bool(review_feedback),
          },
          duration_ms=elapsed,
      )

    except Exception as e:
      elapsed = (time.perf_counter() - start_time) * 1000
      return SubagentResult(
          subagent_name=self.name,
          goal=goal,
          success=False,
          findings="",
          error=f"Code generation failed: {str(e)}",
          duration_ms=elapsed,
      )
