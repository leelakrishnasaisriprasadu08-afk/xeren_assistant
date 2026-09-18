"""SQLite backed session and state persistence."""

from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
from models.base import LLMMessage


class SQLiteSessionStorage:
  """Persists conversation session history to SQLite."""

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
              CREATE TABLE IF NOT EXISTS session_messages (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id TEXT NOT NULL,
                  role TEXT NOT NULL,
                  content TEXT NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
              )
              """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_id ON"
            " session_messages(session_id)"
        )

  def save_message(self, session_id: str, message: LLMMessage) -> None:
    with closing(self._get_connection()) as conn:
      with conn:
        conn.execute(
            "INSERT INTO session_messages (session_id, role, content) VALUES (?,"
            " ?, ?)",
            (session_id, message.role, message.content),
        )

  def get_history(
      self, session_id: str, limit: int = 20
  ) -> List[LLMMessage]:
    with closing(self._get_connection()) as conn:
      cursor = conn.execute(
          "SELECT role, content FROM session_messages WHERE session_id = ?"
          " ORDER BY id DESC LIMIT ?",
          (session_id, limit),
      )
      rows = cursor.fetchall()
      messages = [
          LLMMessage(role=r["role"], content=r["content"])
          for r in reversed(rows)
      ]
      return messages
