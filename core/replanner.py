"""Self-healing and dynamic replanning engine for automated error recovery."""

import json
import re
from typing import Any, Dict, List, Optional
from models.base import BaseLLMProvider, LLMMessage
from security.policies import get_operation_policy
from tools.base import Action, ToolResult
from .dag import DAGAction


class DynamicReplanner:
  """Evaluates runtime failures and produces targeted corrective actions."""

  def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
    self.llm_provider = llm_provider

  def _create_action(
      self,
      action_id: str,
      tool_name: str,
      operation: str,
      parameters: Dict[str, Any],
      reason: str,
      depends_on: Optional[List[str]] = None,
  ) -> DAGAction:
    policy = get_operation_policy(tool_name, operation)
    return DAGAction(
        action_id=action_id,
        tool_name=tool_name,
        operation=operation,
        parameters=parameters,
        required_permission=policy.permission_level,
        risk_level=policy.risk_level,
        reason=reason,
        depends_on=depends_on or [],
    )

  def plan_correction_deterministic(
      self,
      failed_action: Action,
      error_message: str,
      user_query: str,
  ) -> Optional[DAGAction]:
    """Applies deterministic recovery heuristics based on the failure pattern."""
    tool = failed_action.tool_name.lower()
    op = failed_action.operation.lower()
    err = (error_message or "").lower()

    # 1. File Not Found on read_file -> Switch to search_files
    if tool == "filesystem" and op == "read_file" and "not found" in err:
      target_path = failed_action.parameters.get("path", "")
      filename = target_path.split("/")[-1].split("\\")[-1]
      search_term = filename.split(".")[0] if "." in filename else filename
      return self._create_action(
          action_id=f"{failed_action.action_id}_repair",
          tool_name="filesystem",
          operation="search_files",
          parameters={"query": search_term},
          reason=(
              f"Original file '{target_path}' was not found. Searching"
              f" workspace for matching files with pattern '{search_term}'."
          ),
      )

    # 2. Web search returned 0 results or network hiccup -> Broader search query
    if tool == "web_search" and op == "search":
      query = failed_action.parameters.get("query", "")
      simplified = re.sub(r"[^\w\s]", "", query).strip()
      words = simplified.split()
      if len(words) > 3:
        broad_query = " ".join(words[:3])
        return self._create_action(
            action_id=f"{failed_action.action_id}_repair",
            tool_name="web_search",
            operation="search",
            parameters={"query": broad_query, "max_results": 5},
            reason=(
                f"Initial query '{query}' yielded no results. Retrying with"
                f" broader query '{broad_query}'."
            ),
        )

    # 3. GitHub repository not found / invalid repo format -> Search public info
    if tool == "github" and "not found" in err:
      repo = failed_action.parameters.get("repo", "")
      return self._create_action(
          action_id=f"{failed_action.action_id}_repair",
          tool_name="web_search",
          operation="search",
          parameters={"query": f"github repo {repo}", "max_results": 3},
          reason=(
              f"GitHub repo '{repo}' was not accessible. Falling back to web"
              " search."
          ),
      )

    return None

  async def plan_correction(
      self,
      failed_action: Action,
      error_message: str,
      user_query: str,
      prior_results: Dict[str, ToolResult],
  ) -> Optional[DAGAction]:
    """Generates a dynamic repair step using deterministic rules with LLM fallback."""
    # 1. Try deterministic heuristic
    det_action = self.plan_correction_deterministic(
        failed_action, error_message, user_query
    )
    if det_action:
      return det_action

    # 2. LLM-assisted self-healing fallback
    if self.llm_provider:
      try:
        system_prompt = (
            "You are the Dynamic Self-Healing Replanner for Xeren Assistant. An"
            " action failed during execution. Analyze the failure error and"
            " output a single corrective Action in JSON format to recover"
            " progress. Valid tools: filesystem (read_file, list_dir,"
            " search_files), github, web_search, tasks. JSON keys: action_id,"
            " tool_name, operation, parameters, reason."
        )
        user_prompt = (
            f"User Prompt: {user_query}\n"
            f"Failed Action: {failed_action.model_dump_json()}\n"
            f"Error: {error_message}\n"
        )
        resp = await self.llm_provider.generate(
            messages=[LLMMessage(role="user", content=user_prompt)],
            system_instruction=system_prompt,
            temperature=0.0,
        )
        clean = resp.text.strip()
        if "```json" in clean:
          clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
          clean = clean.split("```")[1].split("```")[0].strip()

        data = json.loads(clean)
        return self._create_action(
            action_id=data.get(
                "action_id", f"{failed_action.action_id}_llm_repair"
            ),
            tool_name=data.get("tool_name", "web_search"),
            operation=data.get("operation", "search"),
            parameters=data.get("parameters", {}),
            reason=data.get("reason", "LLM-assisted self-healing recovery"),
        )
      except Exception:
        pass

    return None
