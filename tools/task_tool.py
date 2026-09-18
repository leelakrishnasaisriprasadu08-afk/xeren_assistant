"""Task Tool providing persistent local task/todo management via SQLite."""

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional
from .base import Action, BaseTool, ToolResult


class TaskTool(BaseTool):
  """Local SQLite task and todo manager."""

  name = "tasks"
  description = "Create, list, update, get, and delete tasks in persistent local SQLite storage."
  supported_operations = [
      "create_task",
      "list_tasks",
      "get_task",
      "update_task",
      "delete_task",
  ]

  def __init__(self, db_path: Optional[Path] = None):
    self.db_path = (db_path or Path("data/xeren.sqlite")).resolve()
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
    self._init_db()

  def _get_connection(self) -> sqlite3.Connection:
    conn = sqlite3.connect(str(self.db_path))
    conn.row_factory = sqlite3.Row
    return conn

  def _init_db(self) -> None:
    with closing(self._get_connection()) as conn:
      with conn:
        conn.execute("""
              CREATE TABLE IF NOT EXISTS tasks (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT NOT NULL,
                  description TEXT DEFAULT '',
                  priority TEXT DEFAULT 'medium',
                  status TEXT DEFAULT 'pending',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
              )
              """)

  async def execute(self, action: Action) -> ToolResult:
    start_time = time.perf_counter()
    op = action.operation.lower()
    params = action.parameters or {}

    try:
      with closing(self._get_connection()) as conn:
        with conn:
          if op == "create_task":
            title = params.get("title")
            if not title:
              raise ValueError("Parameter 'title' is required for create_task.")

            description = params.get("description", "")
            priority = params.get("priority", "medium")
            status = params.get("status", "pending")
            now = datetime.now(timezone.utc).isoformat()

            cursor = conn.execute(
                """
                      INSERT INTO tasks (title, description, priority, status, created_at, updated_at)
                      VALUES (?, ?, ?, ?, ?, ?)
                      """,
                (title, description, priority, status, now, now),
            )
            task_id = cursor.lastrowid

            data = {
                "task_id": task_id,
                "title": title,
                "description": description,
                "priority": priority,
                "status": status,
                "created_at": now,
            }

          elif op == "list_tasks":
            status_filter = params.get("status")
            limit = min(int(params.get("limit", 20)), 100)

            if status_filter:
              cursor = conn.execute(
                  """
                          SELECT id, title, description, priority, status, created_at, updated_at
                          FROM tasks WHERE status = ? ORDER BY id DESC LIMIT ?
                          """,
                  (status_filter, limit),
              )
            else:
              cursor = conn.execute(
                  """
                          SELECT id, title, description, priority, status, created_at, updated_at
                          FROM tasks ORDER BY id DESC LIMIT ?
                          """,
                  (limit,),
              )

            rows = cursor.fetchall()
            data = [dict(row) for row in rows]

          elif op == "get_task":
            task_id = params.get("task_id") or params.get("id")
            if not task_id:
              raise ValueError("Parameter 'task_id' is required for get_task.")

            cursor = conn.execute(
                """
                      SELECT id, title, description, priority, status, created_at, updated_at
                      FROM tasks WHERE id = ?
                      """,
                (int(task_id),),
            )
            row = cursor.fetchone()
            if not row:
              raise ValueError(f"Task with ID {task_id} not found.")
            data = dict(row)

          elif op == "update_task":
            task_id = params.get("task_id") or params.get("id")
            if not task_id:
              raise ValueError(
                  "Parameter 'task_id' is required for update_task."
              )

            updates = []
            values = []
            for field in ["title", "description", "priority", "status"]:
              if field in params:
                updates.append(f"{field} = ?")
                values.append(params[field])

            if not updates:
              raise ValueError("No fields provided to update.")

            updates.append("updated_at = ?")
            values.append(datetime.now(timezone.utc).isoformat())
            values.append(int(task_id))

            conn.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", values
            )
            data = {"task_id": int(task_id), "updated": True}

          elif op == "delete_task":
            task_id = params.get("task_id") or params.get("id")
            if not task_id:
              raise ValueError(
                  "Parameter 'task_id' is required for delete_task."
              )

            conn.execute("DELETE FROM tasks WHERE id = ?", (int(task_id),))
            data = {"task_id": int(task_id), "deleted": True}

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
