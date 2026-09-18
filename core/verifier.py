"""Dual-Loop Verification and Validation Engine."""

import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from models.base import BaseLLMProvider, LLMMessage
from tools.base import Action, ToolResult


class VerificationResult(BaseModel):
  """Result of Loop-1 deterministic action validation check."""

  action_id: str
  verified: bool
  feedback: str
  is_retryable: bool = False
  data: Any = None


class SemanticVerificationResult(BaseModel):
  """Result of Loop-2 semantic response validation check."""

  verified: bool
  completeness_score: float = 1.0
  anti_hallucination_passed: bool = True
  feedback: str = "Semantic validation passed."


class Verifier:
  """Dual-Loop Verification Engine (Deterministic Structural + Semantic Completeness)."""

  def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
    self.llm_provider = llm_provider

  def verify_action_result(
      self, action: Action, result: ToolResult
  ) -> VerificationResult:
    """Loop 1: Fast deterministic structural verification."""
    if not result.success:
      is_retryable = "Permission Denied" not in (result.error or "")
      return VerificationResult(
          action_id=action.action_id,
          verified=False,
          feedback=f"Tool execution failed: {result.error}",
          is_retryable=is_retryable,
      )

    op = action.operation.lower()
    tool = action.tool_name.lower()
    data = result.data

    if tool == "filesystem":
      if op == "read_file":
        if not isinstance(data, dict) or "content" not in data:
          return VerificationResult(
              action_id=action.action_id,
              verified=False,
              feedback="Invalid file read response structure.",
              is_retryable=False,
          )
      elif op == "list_dir":
        if not isinstance(data, dict) or "entries" not in data:
          return VerificationResult(
              action_id=action.action_id,
              verified=False,
              feedback="Invalid directory list structure.",
              is_retryable=False,
          )
      elif op in ["write_file", "create_file"]:
        if not isinstance(data, dict) or "bytes_written" not in data:
          return VerificationResult(
              action_id=action.action_id,
              verified=False,
              feedback="File write verification failed: No bytes written confirmation.",
              is_retryable=False,
          )

    elif tool == "tasks":
      if op == "create_task":
        if not isinstance(data, dict) or "task_id" not in data:
          return VerificationResult(
              action_id=action.action_id,
              verified=False,
              feedback="Task creation failed to return a valid task_id.",
              is_retryable=True,
          )
      elif op in ["get_task", "list_tasks"]:
        if data is None:
          return VerificationResult(
              action_id=action.action_id,
              verified=False,
              feedback="Task query returned empty or invalid data.",
              is_retryable=False,
          )

    elif tool == "github":
      if op == "get_repo":
        if not isinstance(data, dict) or not data.get("full_name"):
          return VerificationResult(
              action_id=action.action_id,
              verified=False,
              feedback="GitHub repository metadata is missing or invalid.",
              is_retryable=True,
          )
      elif op == "create_issue":
        if not isinstance(data, dict) or not data.get("issue_number"):
          return VerificationResult(
              action_id=action.action_id,
              verified=False,
              feedback="GitHub issue creation failed to return issue_number.",
              is_retryable=True,
          )
      elif op == "create_pr":
        if not isinstance(data, dict) or not data.get("pr_number"):
          return VerificationResult(
              action_id=action.action_id,
              verified=False,
              feedback="GitHub PR creation failed to return pr_number.",
              is_retryable=True,
          )

    return VerificationResult(
        action_id=action.action_id,
        verified=True,
        feedback="Deterministic validation passed successfully.",
        data=data,
    )

  async def verify_semantic_response(
      self,
      user_prompt: str,
      response_text: str,
      tool_results: Dict[str, ToolResult],
  ) -> SemanticVerificationResult:
    """Loop 2: Semantic verification check assessing response completeness and anti-hallucination."""
    if not response_text or len(response_text.strip()) == 0:
      return SemanticVerificationResult(
          verified=False,
          completeness_score=0.0,
          anti_hallucination_passed=False,
          feedback="Synthesized response is empty.",
      )

    # Check for empty markdown link hallucinations (e.g. `[]()` or `[title]()`)
    if re.search(r"\[[^\]]*\]\(\s*\)", response_text):
      return SemanticVerificationResult(
          verified=False,
          completeness_score=0.5,
          anti_hallucination_passed=False,
          feedback="Response contains broken/empty markdown links.",
      )

    # Check for failed execution claims when data was returned successfully
    if (
        any(res.success for res in tool_results.values())
        and "execution failed" in response_text.lower()
        and "❌" not in response_text
    ):
      return SemanticVerificationResult(
          verified=False,
          completeness_score=0.3,
          anti_hallucination_passed=False,
          feedback="Response incorrectly claims failure when tool executions succeeded.",
      )

    return SemanticVerificationResult(
        verified=True,
        completeness_score=1.0,
        anti_hallucination_passed=True,
        feedback="Semantic verification passed.",
    )
