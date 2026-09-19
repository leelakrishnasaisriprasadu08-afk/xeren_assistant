"""Codebase Tool exposing AST symbol searching, file outlining, and call hierarchy queries."""

import time
from typing import Any, Dict, List, Optional
from codebase.indexer import CodebaseIndexer
from .base import Action, BaseTool, ToolResult


class CodebaseTool(BaseTool):
  """Tool for indexing workspace symbols and querying AST call hierarchies."""

  name = "codebase"
  description = "Index codebase AST symbols, search functions/classes, get file outlines, and inspect call graphs."
  supported_operations = [
      "index_workspace",
      "find_symbol",
      "get_file_outline",
      "find_references",
      "get_call_graph",
  ]

  def __init__(self, indexer: Optional[CodebaseIndexer] = None):
    self.indexer = indexer or CodebaseIndexer()

  async def execute(self, action: Action) -> ToolResult:
    start_time = time.perf_counter()
    op = action.operation.lower()
    params = action.parameters or {}

    try:
      if op == "index_workspace":
        force = bool(params.get("force", False))
        data = self.indexer.index_workspace(force=force)

      elif op == "find_symbol":
        query = params.get("query") or params.get("name") or ""
        stype = params.get("symbol_type") or params.get("type")
        file_pat = params.get("file_pattern") or params.get("file")
        limit = int(params.get("limit", 20))
        data = self.indexer.search_symbols(
            query=query,
            symbol_type=stype,
            file_pattern=file_pat,
            limit=limit,
        )

      elif op == "get_file_outline":
        file_path = params.get("file_path") or params.get("file")
        if not file_path:
          raise ValueError(
              "Parameter 'file_path' is required for get_file_outline."
          )
        data = self.indexer.get_file_outline(file_path=file_path)

      elif op == "find_references":
        target = params.get("symbol_name") or params.get("name") or ""
        if not target:
          raise ValueError(
              "Parameter 'symbol_name' is required for find_references."
          )
        callers = self.indexer.graph.find_callers(target)
        data = [c.model_dump() for c in callers]

      elif op == "get_call_graph":
        target = params.get("symbol_name") or params.get("name") or ""
        if not target:
          raise ValueError(
              "Parameter 'symbol_name' is required for get_call_graph."
          )
        data = self.indexer.get_call_hierarchy(symbol_name=target)

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
