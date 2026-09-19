"""Patch Tool providing test-driven patch generation and verified diff application."""

from pathlib import Path
import time
from typing import Any, Dict, List, Optional
from patching.diff_applier import DiffApplier
from patching.patch_engine import PatchEngine
from .base import Action, BaseTool, ToolResult


class PatchTool(BaseTool):
  """Tool for autonomous TDD patch generation and atomic diff application."""

  name = "patch"
  description = "Generate verified patches with test-driven execution, apply unified diffs, and revert changes."
  supported_operations = [
      "generate_patch",
      "apply_patch",
      "revert_patch",
  ]

  def __init__(self, patch_engine: Optional[PatchEngine] = None):
    self.patch_engine = patch_engine or PatchEngine()

  async def execute(self, action: Action) -> ToolResult:
    start_time = time.perf_counter()
    op = action.operation.lower()
    params = action.parameters or {}

    try:
      if op == "generate_patch":
        target_file = params.get("target_file") or params.get("file")
        instruction = params.get("instruction") or params.get("description")
        test_target = params.get("test_target") or params.get("test_file")
        max_retries = int(params.get("max_retries", 2))
        dry_run = bool(params.get("dry_run", False))

        if not target_file or not instruction:
          raise ValueError(
              "Parameters 'target_file' and 'instruction' are required for"
              " generate_patch."
          )

        patch_res = await self.patch_engine.generate_and_verify_patch(
            target_file=target_file,
            instruction=instruction,
            test_target=test_target,
            max_retries=max_retries,
            dry_run=dry_run,
        )
        data = patch_res.model_dump()

      elif op == "apply_patch":
        target_file = params.get("target_file") or params.get("file")
        patch_diff = params.get("patch_diff") or params.get("diff")
        if not target_file or not patch_diff:
          raise ValueError(
              "Parameters 'target_file' and 'patch_diff' are required for"
              " apply_patch."
          )

        full_path = self.patch_engine.workspace_root / target_file
        success, error = DiffApplier.apply_patch_to_file(full_path, patch_diff)
        if not success:
          raise RuntimeError(error or "Failed to apply patch diff.")
        data = {
            "target_file": target_file,
            "applied": True,
            "status": "Patch successfully applied.",
        }

      elif op == "revert_patch":
        target_file = params.get("target_file") or params.get("file")
        original_content = params.get("original_content")
        if not target_file or original_content is None:
          raise ValueError(
              "Parameters 'target_file' and 'original_content' are required for"
              " revert_patch."
          )

        full_path = self.patch_engine.workspace_root / target_file
        full_path.write_text(original_content, encoding="utf-8")
        data = {
            "target_file": target_file,
            "reverted": True,
            "status": "File reverted to original content.",
        }

      else:
        raise ValueError(
            f"Unsupported operation '{op}' for tool '{self.name}'"
        )

      elapsed = (time.perf_counter() - start_time) * 1000
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=op,
          success=True,
          data=data,
          execution_time_ms=elapsed,
      )

    except Exception as e:
      elapsed = (time.perf_counter() - start_time) * 1000
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=op,
          success=False,
          error=str(e),
          execution_time_ms=elapsed,
      )
