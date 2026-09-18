"""Filesystem Tool providing safe, sandboxed file exploration and modification."""

import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
from security.permission_gate import PathContainmentError, PermissionGate
from .base import Action, BaseTool, ToolResult
from .sandbox import FileSandbox


class FilesystemTool(BaseTool):
  """Sandboxed filesystem tool supporting safe reads and atomic writes with backups."""

  name = "filesystem"
  description = "Safe filesystem tool for inspecting and atomically modifying workspace files and directories."
  supported_operations = [
      "read_file",
      "list_dir",
      "search_files",
      "write_file",
      "create_file",
  ]

  def __init__(
      self,
      workspace_root: Optional[Path] = None,
      permission_gate: Optional[PermissionGate] = None,
      sandbox: Optional[FileSandbox] = None,
  ):
    self.workspace_root = (workspace_root or Path(".").resolve()).resolve()
    self.permission_gate = permission_gate or PermissionGate(
        workspace_root=self.workspace_root
    )
    self.sandbox = sandbox or FileSandbox(workspace_root=self.workspace_root)

  async def execute(self, action: Action) -> ToolResult:
    start_time = time.perf_counter()
    op = action.operation.lower()
    params = action.parameters or {}

    try:
      if op == "read_file":
        rel_path = params.get("path") or params.get("file_path")
        if not rel_path:
          raise ValueError("Parameter 'path' is required for read_file.")

        resolved_path = self.permission_gate.validate_path(rel_path)
        if not resolved_path.is_file():
          raise FileNotFoundError(f"File not found: {rel_path}")

        max_bytes = params.get("max_bytes", 500_000)
        with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
          content = f.read(max_bytes)

        elapsed = (time.perf_counter() - start_time) * 1000
        return ToolResult(
            action_id=action.action_id,
            tool_name=self.name,
            operation=op,
            success=True,
            data={
                "path": str(resolved_path.relative_to(self.workspace_root)),
                "content": content,
                "size_bytes": resolved_path.stat().st_size,
            },
            execution_time_ms=elapsed,
        )

      elif op == "list_dir":
        rel_path = (
            params.get("path")
            or params.get("directory")
            or params.get("dir")
            or "."
        )
        resolved_path = self.permission_gate.validate_path(rel_path)
        if not resolved_path.is_dir():
          raise NotADirectoryError(f"Directory not found: {rel_path}")

        entries = []
        for entry in os.scandir(resolved_path):
          entries.append({
              "name": entry.name,
              "is_dir": entry.is_dir(),
              "size": entry.stat().st_size if entry.is_file() else None,
          })

        elapsed = (time.perf_counter() - start_time) * 1000
        return ToolResult(
            action_id=action.action_id,
            tool_name=self.name,
            operation=op,
            success=True,
            data={
                "directory": str(
                    resolved_path.relative_to(self.workspace_root)
                ),
                "entries": sorted(entries, key=lambda x: (not x["is_dir"], x["name"])),
            },
            execution_time_ms=elapsed,
        )

      elif op == "search_files":
        query = (params.get("query") or params.get("pattern") or "").lower()
        max_results = params.get("max_results", 50)
        matches = []

        for root, dirs, files in os.walk(self.workspace_root):
          dirs[:] = [
              d
              for d in dirs
              if d
              not in [
                  ".git",
                  "__pycache__",
                  ".venv",
                  "venv",
                  "node_modules",
                  ".pytest_cache",
                  ".xeren_backups",
              ]
          ]
          for f in files:
            file_rel = str(
                (Path(root) / f).resolve().relative_to(self.workspace_root)
            )
            if query in f.lower() or query in file_rel.lower():
              matches.append(file_rel)
              if len(matches) >= max_results:
                break
          if len(matches) >= max_results:
            break

        elapsed = (time.perf_counter() - start_time) * 1000
        return ToolResult(
            action_id=action.action_id,
            tool_name=self.name,
            operation=op,
            success=True,
            data={"query": query, "matches": matches},
            execution_time_ms=elapsed,
        )

      elif op in ["write_file", "create_file"]:
        rel_path = params.get("path") or params.get("file_path")
        if not rel_path:
          raise ValueError(f"Parameter 'path' is required for {op}.")

        content = params.get("content", "")
        resolved_path = self.permission_gate.validate_path(rel_path)

        # Create snapshot backup if file already exists
        backup_path = self.sandbox.create_backup(resolved_path)

        # Atomically write to destination
        self.sandbox.atomic_write(resolved_path, content)

        elapsed = (time.perf_counter() - start_time) * 1000
        return ToolResult(
            action_id=action.action_id,
            tool_name=self.name,
            operation=op,
            success=True,
            data={
                "path": str(resolved_path.relative_to(self.workspace_root)),
                "bytes_written": len(content.encode("utf-8")),
                "backup_created": str(backup_path) if backup_path else None,
                "is_new_file": backup_path is None,
            },
            execution_time_ms=elapsed,
        )

      else:
        raise ValueError(
            f"Unsupported operation '{op}' for tool '{self.name}'"
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
