"""Specialized Autonomous Test-Driven Patching Subagent."""

import time
from typing import Any, Dict, List, Optional
from codebase.indexer import CodebaseIndexer
from models.base import BaseLLMProvider
from patching.patch_engine import PatchEngine, PatchResult
from tools.registry import ToolRegistry
from .base import BaseSubagent, SubagentResult


class PatchSubagent(BaseSubagent):
  """Autonomous subagent specializing in AST-guided test-driven code patching and healing."""

  name = "patcher"
  role_description = "Investigates AST code hierarchies, drafts surgical fixes, and verifies patches using automated tests."
  allowed_tools = ["codebase", "patch", "filesystem", "shell"]

  def __init__(
      self,
      llm_provider: BaseLLMProvider,
      tool_registry: Optional[ToolRegistry] = None,
      patch_engine: Optional[PatchEngine] = None,
      indexer: Optional[CodebaseIndexer] = None,
  ):
    super().__init__(llm_provider=llm_provider, tool_registry=tool_registry)
    self.patch_engine = patch_engine or PatchEngine(
        llm_provider=self.llm_provider
    )
    self.indexer = indexer or CodebaseIndexer()

  async def run(
      self, goal: str, context: Optional[Dict[str, Any]] = None
  ) -> SubagentResult:
    start_time = time.perf_counter()
    ctx = context or {}
    target_file = ctx.get("target_file") or ctx.get("file", "")
    test_target = ctx.get("test_target") or ctx.get("test_file")
    dry_run = bool(ctx.get("dry_run", False))

    # If target_file not specified, attempt to locate via AST indexer
    if not target_file:
      search_res = self.indexer.search_symbols(query=goal.split()[0], limit=1)
      if search_res:
        target_file = search_res[0]["file_path"]

    if not target_file:
      elapsed = (time.perf_counter() - start_time) * 1000
      return SubagentResult(
          subagent_name=self.name,
          goal=goal,
          success=False,
          findings=(
              "Could not identify target file for patching from task"
              " description."
          ),
          structured_data={
              "error": (
                  "Provide explicit 'target_file' parameter for patch"
                  " generation."
              )
          },
          duration_ms=elapsed,
          error="Missing target_file parameter",
      )

    patch_res: PatchResult = (
        await self.patch_engine.generate_and_verify_patch(
            target_file=target_file,
            instruction=goal,
            test_target=test_target,
            dry_run=dry_run,
        )
    )

    elapsed = (time.perf_counter() - start_time) * 1000
    if patch_res.tests_passed:
      findings = (
          f"Successfully generated and test-verified patch for"
          f" {patch_res.target_file} in {patch_res.attempts} attempt(s)."
      )
    else:
      findings = (
          f"Patch generation for {patch_res.target_file} failed test"
          f" verification: {patch_res.error}"
      )

    return SubagentResult(
        subagent_name=self.name,
        goal=goal,
        success=patch_res.success,
        findings=findings,
        structured_data=patch_res.model_dump(),
        duration_ms=elapsed,
        error=patch_res.error,
    )
