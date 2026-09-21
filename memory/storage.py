"""SQLite backed session and state persistence with single-sentence chat summaries."""

from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional
from models.base import LLMMessage


def generate_single_sentence_title(query: str, intent_str: Optional[str] = None) -> str:
  """Generates a distinctive, single-sentence episodic summary title for a chat conversation."""
  q = query.strip()
  if not q:
    return "New Autonomous Chat Session"

  # Clean common command prefixes
  clean_q = re.sub(
      r"^(can you|please|could you|i want to|i need to|help me|search web for|search web|check|build a website for|build a|run|save my login for)\s+",
      "",
      q,
      flags=re.IGNORECASE,
  ).strip()

  if not clean_q:
    clean_q = q

  # Capitalize properly
  clean_q = clean_q[0].upper() + clean_q[1:] if len(clean_q) > 1 else clean_q.upper()

  # Construct sentence-style title
  if "website" in q.lower() or "portfolio" in q.lower():
    return f"Autonomous Web Scaffolding and Deployment for {clean_q}"
  elif "search" in q.lower() or "find" in q.lower() or "what is" in q.lower():
    return f"Verified Intelligence & Deep Research on {clean_q}"
  elif "health" in q.lower() or "server" in q.lower() or "port" in q.lower():
    return f"System Health & Infrastructure Diagnostics for {clean_q}"
  elif "login" in q.lower() or "credential" in q.lower() or "vault" in q.lower():
    return f"Credential Enclave Security & Account Gateway for {clean_q}"
  elif "voice" in q.lower() or "speech" in q.lower() or "speak" in q.lower():
    return f"Voice Studio Speech Processing & Vocal Synthesis for {clean_q}"
  elif "task" in q.lower():
    return f"Task Scheduling and Autonomous Workflow Execution for {clean_q}"
  elif len(clean_q.split()) <= 4:
    return f"Autonomous Execution and Guidance on {clean_q}"
  else:
    # Truncate clean sentence if long
    words = clean_q.split()
    if len(words) > 10:
      clean_q = " ".join(words[:10]) + "..."
    return f"Session: {clean_q}"


class SQLiteSessionStorage:
  """Persists conversation session history and single-sentence episodic metadata to SQLite."""

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

        conn.execute("""
              CREATE TABLE IF NOT EXISTS chat_sessions (
                  session_id TEXT PRIMARY KEY,
                  title TEXT NOT NULL,
                  summary TEXT,
                  first_query TEXT,
                  last_intent TEXT,
                  tools_used TEXT DEFAULT '[]',
                  message_count INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
              )
              """)

  def save_message(
      self,
      session_id: str,
      message: LLMMessage,
      intent_str: Optional[str] = None,
      tools_used: Optional[List[str]] = None,
  ) -> None:
    """Saves a message and automatically maintains the single-sentence session metadata."""
    tools_json = json.dumps(tools_used or [])
    with closing(self._get_connection()) as conn:
      with conn:
        # 1. Insert message
        conn.execute(
            "INSERT INTO session_messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, message.role, message.content),
        )

        # 2. Check if session already exists
        cursor = conn.execute(
            "SELECT session_id, title, message_count, tools_used FROM chat_sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()

        if not row:
          title = generate_single_sentence_title(message.content, intent_str)
          conn.execute(
              """
              INSERT INTO chat_sessions (
                  session_id, title, summary, first_query, last_intent, tools_used, message_count, updated_at
              ) VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
              """,
              (
                  session_id,
                  title,
                  f"Conversation initiated: {title}",
                  message.content[:200],
                  intent_str or "GENERAL",
                  tools_json,
              ),
          )
        else:
          new_count = row["message_count"] + 1
          existing_tools = json.loads(row["tools_used"] or "[]")
          if tools_used:
            for t in tools_used:
              if t not in existing_tools:
                existing_tools.append(t)
          conn.execute(
              """
              UPDATE chat_sessions 
              SET message_count = ?, tools_used = ?, updated_at = CURRENT_TIMESTAMP,
                  last_intent = COALESCE(?, last_intent)
              WHERE session_id = ?
              """,
              (new_count, json.dumps(existing_tools), intent_str, session_id),
          )

  def get_history(
      self, session_id: str, limit: int = 50
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

  def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
    """Returns all saved chat sessions ordered by most recent activity."""
    with closing(self._get_connection()) as conn:
      cursor = conn.execute(
          """
          SELECT session_id, title, summary, first_query, last_intent, tools_used, 
                 message_count, created_at, updated_at
          FROM chat_sessions 
          ORDER BY updated_at DESC LIMIT ?
          """,
          (limit,),
      )
      rows = cursor.fetchall()
      results = []
      for r in rows:
        results.append({
            "session_id": r["session_id"],
            "title": r["title"],
            "summary": r["summary"],
            "first_query": r["first_query"],
            "last_intent": r["last_intent"],
            "tools_used": json.loads(r["tools_used"] or "[]"),
            "message_count": r["message_count"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        })
      return results

  def get_session_details(self, session_id: str) -> Optional[Dict[str, Any]]:
    """Fetches session metadata plus the chronological message log."""
    with closing(self._get_connection()) as conn:
      cursor = conn.execute(
          """
          SELECT session_id, title, summary, first_query, last_intent, tools_used, 
                 message_count, created_at, updated_at
          FROM chat_sessions WHERE session_id = ?
          """,
          (session_id,),
      )
      meta = cursor.fetchone()
      if not meta:
        return None

      msg_cursor = conn.execute(
          "SELECT id, role, content, created_at FROM session_messages WHERE session_id = ? ORDER BY id ASC",
          (session_id,),
      )
      msg_rows = msg_cursor.fetchall()
      messages = [{
          "id": m["id"],
          "role": m["role"],
          "content": m["content"],
          "created_at": m["created_at"],
      } for m in msg_rows]

      session_dict = {
          "session_id": meta["session_id"],
          "title": meta["title"],
          "summary": meta["summary"],
          "first_query": meta["first_query"],
          "last_intent": meta["last_intent"],
          "tools_used": json.loads(meta["tools_used"] or "[]"),
          "message_count": meta["message_count"],
          "created_at": meta["created_at"],
          "updated_at": meta["updated_at"],
      }
      return {
          **session_dict,
          "session": session_dict,
          "messages": messages,
      }

  def rename_session(self, session_id: str, new_title: str) -> bool:
    """Updates the single-sentence title of a chat session."""
    with closing(self._get_connection()) as conn:
      with conn:
        cursor = conn.execute(
            "UPDATE chat_sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
            (new_title.strip(), session_id),
        )
        return cursor.rowcount > 0

  def delete_session(self, session_id: str) -> bool:
    """Deletes a session and all its associated messages."""
    with closing(self._get_connection()) as conn:
      with conn:
        conn.execute("DELETE FROM session_messages WHERE session_id = ?", (session_id,))
        cursor = conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
        return cursor.rowcount > 0

  def clear_all_history(self) -> int:
    """Clears all conversation records and resets the archive."""
    with closing(self._get_connection()) as conn:
      with conn:
        conn.execute("DELETE FROM session_messages")
        cursor = conn.execute("DELETE FROM chat_sessions")
        return cursor.rowcount
