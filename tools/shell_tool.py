"""Sandboxed Shell Command Tool with strict command blacklisting and bounded execution."""

import asyncio
from pathlib import Path
import re
import sys
import time
from typing import List, Optional
from config.settings import get_settings
from security.secrets import RedactionEngine
from .base import Action, BaseTool, ToolResult

# Hard-blocked dangerous command patterns
DANGEROUS_COMMAND_PATTERNS = [
    r"\brm\s+-[rRfF]*\s+[/~]",  # rm -rf / or ~
    r"\bmkfs\b",  # disk format
    r"\bformat\s+[a-zA-Z]:",  # format drive
    r"\bdel\s+/[sSqQ]\s+[a-zA-Z]:\\",  # del /s root drive
    r"\bdiskpart\b",  # disk partitioning
    r"\bshutdown\b",  # system shutdown
    r":\(\)\s*\{\s*:\|:&\s*\};:",  # fork bomb
    r"\bchmod\s+-R\s+777\s+/",  # global chmod
    r"\bdd\s+if=.*of=/dev/",  # raw device write
]


class DangerousCommandError(Exception):
  """Raised when a command matches a blocked destructive pattern."""

  pass


class ShellTool(BaseTool):
  """Executes shell commands within the sandboxed workspace directory."""

  name = "shell"
  description = "Executes shell commands within the workspace sandbox."
  supported_operations: List[str] = ["execute_command"]

  def __init__(
      self,
      workspace_root: Optional[Path] = None,
      max_output_bytes: int = 50000,
  ):
    settings = get_settings()
    self.workspace_root = (workspace_root or settings.workspace_root).resolve()
    self.max_output_bytes = max_output_bytes
    self.redaction_engine = RedactionEngine()

  def _check_dangerous_command(self, cmd: str) -> None:
    for pattern in DANGEROUS_COMMAND_PATTERNS:
      if re.search(pattern, cmd, re.IGNORECASE):
        raise DangerousCommandError(
            f"Command '{cmd}' is blocked by security policy: matches dangerous"
            f" pattern '{pattern}'"
        )

  async def execute(self, action: Action) -> ToolResult:
    start_time = time.perf_counter()
    op = action.operation.lower()

    if op != "execute_command":
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=False,
          error=f"Unsupported shell operation: {action.operation}",
      )

    command = action.parameters.get("command", "").strip()
    if not command:
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=False,
          error="Parameter 'command' cannot be empty.",
      )

    # 1. Check dangerous command blacklist
    try:
      self._check_dangerous_command(command)
    except DangerousCommandError as e:
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=False,
          error=str(e),
      )

    timeout_sec = float(action.parameters.get("timeout", action.timeout or 15.0))

    # 2. Execute process in sandboxed CWD
    try:
      proc = await asyncio.create_subprocess_shell(
          command,
          stdout=asyncio.subprocess.PIPE,
          stderr=asyncio.subprocess.PIPE,
          cwd=str(self.workspace_root),
      )

      stdout_bytes, stderr_bytes = await asyncio.wait_for(
          proc.communicate(), timeout=timeout_sec
      )

      stdout_str = stdout_bytes.decode("utf-8", errors="replace")[
          : self.max_output_bytes
      ]
      stderr_str = stderr_bytes.decode("utf-8", errors="replace")[
          : self.max_output_bytes
      ]

      # Redact secrets in outputs
      stdout_clean = self.redaction_engine.redact_text(stdout_str)
      stderr_clean = self.redaction_engine.redact_text(stderr_str)

      elapsed = (time.perf_counter() - start_time) * 1000
      is_success = proc.returncode == 0

      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=is_success,
          data={
              "command": command,
              "exit_code": proc.returncode,
              "stdout": stdout_clean,
              "stderr": stderr_clean,
          },
          error=(
              None
              if is_success
              else f"Process exited with code {proc.returncode}: {stderr_clean.strip() or stdout_clean.strip()}"
          ),
          execution_time_ms=elapsed,
      )

    except asyncio.TimeoutError:
      elapsed = (time.perf_counter() - start_time) * 1000
      try:
        proc.kill()
      except Exception:
        pass
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=False,
          error=f"Command '{command}' timed out after {timeout_sec}s.",
          execution_time_ms=elapsed,
      )
    except Exception as e:
      elapsed = (time.perf_counter() - start_time) * 1000
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=False,
          error=f"Shell execution error: {str(e)}",
          execution_time_ms=elapsed,
      )
