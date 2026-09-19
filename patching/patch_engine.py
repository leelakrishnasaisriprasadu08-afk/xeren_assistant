"""Autonomous Test-Driven Patch Engine with iterative self-healing test loop."""

import asyncio
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from codebase.indexer import CodebaseIndexer
from config.settings import Settings, get_settings
from models.base import BaseLLMProvider, LLMMessage
from models.provider import get_default_llm_provider
from security.diff_engine import DiffEngine
from .diff_applier import DiffApplier


class PatchResult(BaseModel):
  """Result of an autonomous test-driven patch generation run."""

  target_file: str
  instruction: str
  patch_diff: str
  tests_passed: bool
  test_output: str
  attempts: int
  applied: bool
  success: bool
  error: Optional[str] = None
  elapsed_ms: float = 0.0


class PatchEngine:
  """Orchestrates test-driven code modifications with sandboxed verification and self-healing."""

  def __init__(
      self,
      workspace_root: Optional[Path] = None,
      llm_provider: Optional[BaseLLMProvider] = None,
      indexer: Optional[CodebaseIndexer] = None,
      settings: Optional[Settings] = None,
  ):
    self.settings = settings or get_settings()
    self.workspace_root = (
        workspace_root or self.settings.workspace_root
    ).resolve()
    self.llm_provider = llm_provider or get_default_llm_provider(self.settings)
    self.indexer = indexer or CodebaseIndexer(
        workspace_root=self.workspace_root
    )

  async def _run_tests(
      self, test_target: Optional[str] = None, timeout: float = 30.0
  ) -> Tuple[bool, str]:
    """Executes pytest asynchronously against the target test suite."""
    cmd = [sys.executable, "-m", "pytest"]
    if test_target:
      cmd.append(test_target)
    else:
      cmd.extend(["-q", "--tb=short"])

    try:
      proc = await asyncio.create_subprocess_exec(
          *cmd,
          cwd=str(self.workspace_root),
          stdout=asyncio.subprocess.PIPE,
          stderr=asyncio.subprocess.STDOUT,
      )
      stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
      output = stdout.decode("utf-8", errors="replace")
      passed = proc.returncode == 0
      return passed, output
    except asyncio.TimeoutError:
      return False, f"Test execution timed out after {timeout} seconds."
    except Exception as e:
      return False, f"Failed to execute tests: {str(e)}"

  async def generate_and_verify_patch(
      self,
      target_file: str,
      instruction: str,
      test_target: Optional[str] = None,
      max_retries: int = 2,
      dry_run: bool = False,
  ) -> PatchResult:
    """Generates a patch, applies it to a staged copy, runs tests, and iteratively heals if failed."""
    start_time = time.perf_counter()
    full_path = (self.workspace_root / target_file).resolve()

    if not full_path.exists():
      return PatchResult(
          target_file=target_file,
          instruction=instruction,
          patch_diff="",
          tests_passed=False,
          test_output="",
          attempts=0,
          applied=False,
          success=False,
          error=f"Target file '{target_file}' does not exist.",
      )

    original_code = full_path.read_text(encoding="utf-8")
    symbols = self.indexer.get_file_outline(target_file)
    context_str = f"Symbols in {target_file}:\n" + "\n".join(
        f"- {s.get('type')}: {s.get('name')} (lines {s.get('line_start')}-{s.get('line_end')})"
        for s in symbols[:20]
    )

    backup_map: Dict[str, str] = {str(full_path): original_code}
    last_test_output = ""
    last_diff = ""
    tests_passed = False
    attempt = 0

    system_prompt = (
        "You are an expert Python software engineer specializing in Test-Driven"
        " Development (TDD) and surgical bug-fixing.\n"
        "Your goal is to modify the provided source code to satisfy the user's"
        " instruction.\n"
        "Provide ONLY the full updated code or unified diff for the target"
        " file. Do not include conversational text or explanations outside the"
        " code block."
    )

    for attempt in range(1, max_retries + 2):
      if attempt == 1:
        user_prompt = f"""Target File: {target_file}
Instruction: {instruction}

{context_str}

Existing Code:
```python
{original_code}
```

Write the complete updated Python code for {target_file} that fulfills the instruction."""
      else:
        user_prompt = f"""Your previous patch caused test failures.

Target File: {target_file}
Instruction: {instruction}

Test Failure Output:
{last_test_output}

Current Code:
```python
{full_path.read_text(encoding='utf-8')}
```

Fix the errors and output the corrected full Python code for {target_file}."""

      # 1. Generate patch from LLM
      llm_resp = await self.llm_provider.generate(
          messages=[LLMMessage(role="user", content=user_prompt)],
          system_instruction=system_prompt,
          temperature=0.1,
      )

      raw_text = llm_resp.text.strip()
      # Extract code block if formatted with markdown
      if "```python" in raw_text:
        new_code = raw_text.split("```python")[1].split("```")[0].strip() + "\n"
      elif "```" in raw_text:
        new_code = raw_text.split("```")[1].split("```")[0].strip() + "\n"
      else:
        new_code = raw_text + "\n"

      # 2. Stage new code to target file
      full_path.write_text(new_code, encoding="utf-8")
      last_diff = DiffEngine.generate_unified_diff(
          old_content=original_code,
          new_content=new_code,
          file_path=target_file,
      )

      # 3. Run test verification
      tests_passed, test_output = await self._run_tests(test_target=test_target)
      last_test_output = test_output

      if tests_passed:
        break

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    if dry_run or not tests_passed:
      # Revert to original content if dry-run or failed
      DiffApplier.rollback_backups(backup_map)
      applied = False
    else:
      applied = True

    return PatchResult(
        target_file=target_file,
        instruction=instruction,
        patch_diff=last_diff,
        tests_passed=tests_passed,
        test_output=last_test_output,
        attempts=attempt,
        applied=applied,
        success=tests_passed,
        elapsed_ms=elapsed_ms,
        error=None if tests_passed else "Tests failed after max retries.",
    )
