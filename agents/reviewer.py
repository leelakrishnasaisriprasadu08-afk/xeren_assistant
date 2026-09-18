"""Autonomous Code Reviewer Subagent for static code analysis, security review, and diff audits."""

import time
from typing import Any, Dict, List, Optional
from models.base import BaseLLMProvider, LLMMessage
from security.policies import PermissionLevel, RiskLevel
from tools.base import Action, ToolResult
from tools.registry import ToolRegistry
from .base import BaseSubagent, SubagentResult


class CodeReviewerSubagent(BaseSubagent):
  """Specialized agent focused on code quality, security audits, diff reviews, and bug detection."""

  name = "code_reviewer"
  role_description = "Inspects code files, modifications, and diffs for security vulnerabilities, race conditions, edge cases, and design flaws."
  allowed_tools: List[str] = ["filesystem"]

  async def run(
      self, goal: str, context: Optional[Dict[str, Any]] = None
  ) -> SubagentResult:
    start_time = time.perf_counter()
    ctx = context or {}
    actions_executed = []

    file_path = ctx.get("file_path") or ctx.get("path")
    diff_text = ctx.get("diff") or ctx.get("diff_preview", "")
    code_content = ctx.get("content", "")

    # If a file_path is specified but content is missing, read file via ToolRegistry
    if file_path and not code_content and not diff_text and self.tool_registry:
      read_action = Action(
          action_id=f"reviewer_read_01",
          tool_name="filesystem",
          operation="read_file",
          parameters={"path": file_path},
          required_permission=PermissionLevel.ALLOWED,
          risk_level=RiskLevel.LOW,
          reason=f"Read target file {file_path} for code review",
      )
      read_res = await self.tool_registry.execute_action(read_action)
      actions_executed.append(
          {"action": read_action.model_dump(), "success": read_res.success}
      )
      if read_res.success and read_res.data:
        code_content = read_res.data.get("content", "")

    system_prompt = (
        "You are the Xeren Expert Code Reviewer and Security Auditor. "
        "Review the target code or diff against: (1) Security & Path Traversal / Injections, "
        "(2) Edge cases & Race conditions, (3) Clean Architecture & Typings. "
        "Output a structured review with Severity ratings (CRITICAL / HIGH / MEDIUM / LOW / PASSED) and concrete recommendations."
    )

    review_target = (
        f"Diff to Review:\n```diff\n{diff_text}\n```"
        if diff_text
        else f"Source Code ({file_path or 'Snippet'}):\n```\n{code_content}\n```"
    )

    user_prompt = (
        f"Review Goal: {goal}\n\n"
        f"{review_target}\n\n"
        "Provide a concise, professional audit report."
    )

    try:
      response = await self.llm_provider.generate(
          messages=[LLMMessage(role="user", content=user_prompt)],
          system_instruction=system_prompt,
          temperature=0.1,
      )
      findings = response.text.strip()
      elapsed = (time.perf_counter() - start_time) * 1000

      # Check if issues found
      has_critical = "CRITICAL" in findings or "HIGH" in findings

      return SubagentResult(
          subagent_name=self.name,
          goal=goal,
          success=True,
          findings=findings,
          structured_data={
              "target_file": file_path,
              "has_critical_issues": has_critical,
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
          error=f"Code review failed: {str(e)}",
          actions_executed=actions_executed,
          duration_ms=elapsed,
      )
