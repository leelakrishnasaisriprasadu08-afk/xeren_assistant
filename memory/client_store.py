"""Persistent SQLite storage for Client Profiles, Inquiry Threads, and Messages."""

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Union
import uuid
from pydantic import BaseModel, Field


class ClientProfile(BaseModel):
  """Representation of an external client or customer profile."""

  client_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
  name: str
  email: str
  company: Optional[str] = None
  communication_tone: str = "professional"  # "professional", "technical", "empathetic", "concise"
  notes: str = ""
  status: str = "active"  # "active", "vip", "archived"
  created_at: str = Field(
      default_factory=lambda: datetime.now(timezone.utc).isoformat()
  )


class ClientThread(BaseModel):
  """Representation of an ongoing client conversation or inquiry thread."""

  thread_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
  client_id: Optional[str] = None
  client_name: str = "Client"
  client_email: Optional[str] = None
  subject: str = "Update"
  channel: str = "email"  # "email", "webhook", "github", "portal"
  inquiry_text: str = ""
  status: str = "open"  # "open", "drafted", "sent", "resolved"
  summary: Optional[str] = None
  created_at: str = Field(
      default_factory=lambda: datetime.now(timezone.utc).isoformat()
  )


class ClientMessage(BaseModel):
  """A single message exchanged within a client thread."""

  message_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
  thread_id: str
  sender: str = "client"  # "client" or "assistant" / "xeren"
  recipient: str = "xeren"
  content: str = ""
  body: Optional[str] = None
  channel: str = "email"
  status: str = "draft"  # "draft", "sent", "failed"
  metadata: Dict[str, Any] = Field(default_factory=dict)
  created_at: str = Field(
      default_factory=lambda: datetime.now(timezone.utc).isoformat()
  )

  def __init__(self, **data: Any):
    if "body" in data and not data.get("content"):
      data["content"] = data["body"]
    elif "content" in data and not data.get("body"):
      data["body"] = data["content"]
    super().__init__(**data)


class ClientStore:
  """Persistent SQLite CRM store for managing client profiles, threads, and communications."""

  def __init__(self, db_path: Optional[Union[str, Path]] = None):
    self.db_path = Path(db_path or "data/xeren.sqlite").resolve()
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
              CREATE TABLE IF NOT EXISTS clients (
                  client_id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  email TEXT NOT NULL,
                  company TEXT,
                  communication_tone TEXT,
                  notes TEXT,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL
              )
              """)
        conn.execute("""
              CREATE TABLE IF NOT EXISTS client_threads (
                  thread_id TEXT PRIMARY KEY,
                  client_id TEXT,
                  client_name TEXT NOT NULL,
                  client_email TEXT,
                  subject TEXT NOT NULL,
                  channel TEXT NOT NULL,
                  inquiry_text TEXT,
                  status TEXT NOT NULL,
                  summary TEXT,
                  created_at TEXT NOT NULL
              )
              """)
        conn.execute("""
              CREATE TABLE IF NOT EXISTS client_messages (
                  message_id TEXT PRIMARY KEY,
                  thread_id TEXT NOT NULL,
                  sender TEXT NOT NULL,
                  recipient TEXT NOT NULL,
                  content TEXT NOT NULL,
                  channel TEXT,
                  status TEXT NOT NULL,
                  metadata TEXT,
                  created_at TEXT NOT NULL
              )
              """)

  def create_client(
      self,
      name: str,
      email: str,
      company: Optional[str] = None,
      communication_tone: str = "professional",
      notes: str = "",
      status: str = "active",
  ) -> ClientProfile:
    profile = ClientProfile(
        name=name,
        email=email,
        company=company,
        communication_tone=communication_tone,
        notes=notes,
        status=status,
    )
    with closing(self._get_connection()) as conn:
      with conn:
        conn.execute(
            """
                  INSERT OR REPLACE INTO clients (client_id, name, email, company, communication_tone, notes, status, created_at)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                  """,
            (
                profile.client_id,
                profile.name,
                profile.email,
                profile.company,
                profile.communication_tone,
                profile.notes,
                profile.status,
                profile.created_at,
            ),
        )
    return profile

  def get_client(self, client_id_or_name: str) -> Optional[ClientProfile]:
    with closing(self._get_connection()) as conn:
      cursor = conn.execute(
          "SELECT * FROM clients WHERE client_id = ? OR name LIKE ? OR email = ?",
          (client_id_or_name, f"%{client_id_or_name}%", client_id_or_name),
      )
      row = cursor.fetchone()
      if not row:
        return None
      return ClientProfile(**dict(row))

  def get_client_by_email(self, email: str) -> Optional[ClientProfile]:
    with closing(self._get_connection()) as conn:
      cursor = conn.execute("SELECT * FROM clients WHERE email = ?", (email,))
      row = cursor.fetchone()
      if not row:
        return None
      return ClientProfile(**dict(row))

  def list_clients(self, limit: int = 50) -> List[ClientProfile]:
    with closing(self._get_connection()) as conn:
      cursor = conn.execute("SELECT * FROM clients ORDER BY created_at DESC LIMIT ?", (limit,))
      return [ClientProfile(**dict(r)) for r in cursor.fetchall()]

  def update_client(self, client_id: str, **kwargs: Any) -> bool:
    if not kwargs:
      return False
    keys = list(kwargs.keys())
    set_clause = ", ".join([f"{k} = ?" for k in keys])
    values = list(kwargs.values()) + [client_id]
    with closing(self._get_connection()) as conn:
      with conn:
        cursor = conn.execute(
            f"UPDATE clients SET {set_clause} WHERE client_id = ?", values
        )
        return cursor.rowcount > 0

  def create_thread(
      self,
      client_id: Optional[str] = None,
      subject: str = "Update",
      channel: str = "email",
      client_name: str = "Client",
      inquiry_text: str = "",
      client_email: Optional[str] = None,
      **kwargs: Any,
  ) -> ClientThread:
    # Handle swapped positional arguments if called as create_thread(client_name, subject, inquiry_text)
    if client_id and not client_name and "@" not in client_id:
      pass
    c_name = kwargs.get("name") or client_name
    if client_id and not inquiry_text and not client_email:
      # If first param was passed as client_name
      c_prof = self.get_client(client_id)
      if c_prof:
        c_name = c_prof.name
        client_email = c_prof.email

    thread = ClientThread(
        client_id=client_id,
        client_name=c_name,
        client_email=client_email,
        subject=subject,
        channel=channel,
        inquiry_text=inquiry_text,
    )
    with closing(self._get_connection()) as conn:
      with conn:
        conn.execute(
            """
                  INSERT INTO client_threads (thread_id, client_id, client_name, client_email, subject, channel, inquiry_text, status, summary, created_at)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                  """,
            (
                thread.thread_id,
                thread.client_id,
                thread.client_name,
                thread.client_email,
                thread.subject,
                thread.channel,
                thread.inquiry_text,
                thread.status,
                thread.summary,
                thread.created_at,
            ),
        )
    return thread

  def get_thread(self, thread_id: str) -> Optional[ClientThread]:
    with closing(self._get_connection()) as conn:
      cursor = conn.execute("SELECT * FROM client_threads WHERE thread_id = ?", (thread_id,))
      row = cursor.fetchone()
      if not row:
        return None
      return ClientThread(**dict(row))

  def list_threads(
      self,
      client_id: Optional[str] = None,
      status: Optional[str] = None,
      limit: int = 50,
  ) -> List[ClientThread]:
    with closing(self._get_connection()) as conn:
      query = "SELECT * FROM client_threads WHERE 1=1"
      params: List[Any] = []
      if client_id:
        query += " AND client_id = ?"
        params.append(client_id)
      if status:
        query += " AND status = ?"
        params.append(status)
      query += " ORDER BY created_at DESC LIMIT ?"
      params.append(limit)
      cursor = conn.execute(query, params)
      return [ClientThread(**dict(r)) for r in cursor.fetchall()]

  def update_thread_status(
      self, thread_id: str, status: str, summary: Optional[str] = None
  ) -> bool:
    with closing(self._get_connection()) as conn:
      with conn:
        if summary:
          cursor = conn.execute(
              "UPDATE client_threads SET status = ?, summary = ? WHERE thread_id = ?",
              (status, summary, thread_id),
          )
        else:
          cursor = conn.execute(
              "UPDATE client_threads SET status = ? WHERE thread_id = ?",
              (status, thread_id),
          )
        return cursor.rowcount > 0

  def save_message(
      self,
      thread_id: str,
      sender: str = "client",
      recipient: str = "xeren",
      content: str = "",
      body: Optional[str] = None,
      channel: str = "email",
      status: str = "draft",
      metadata: Optional[Dict[str, Any]] = None,
  ) -> ClientMessage:
    msg_content = content or body or ""
    meta_dict = metadata or {}
    meta_json = json.dumps(meta_dict)
    msg = ClientMessage(
        thread_id=thread_id,
        sender=sender,
        recipient=recipient,
        content=msg_content,
        body=msg_content,
        channel=channel,
        status=status,
        metadata=meta_dict,
    )
    with closing(self._get_connection()) as conn:
      with conn:
        conn.execute(
            """
                  INSERT INTO client_messages (message_id, thread_id, sender, recipient, content, channel, status, metadata, created_at)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                  """,
            (
                msg.message_id,
                msg.thread_id,
                msg.sender,
                msg.recipient,
                msg.content,
                msg.channel,
                msg.status,
                meta_json,
                msg.created_at,
            ),
        )
        if status in ["drafted", "sent"]:
          conn.execute(
              "UPDATE client_threads SET status = ? WHERE thread_id = ?",
              (status, thread_id),
          )
    return msg

  def add_message(
      self,
      thread_id: str,
      sender: str = "client",
      body: str = "",
      recipient: str = "xeren",
      content: Optional[str] = None,
      channel: str = "email",
      status: str = "draft",
      metadata: Optional[Dict[str, Any]] = None,
  ) -> ClientMessage:
    return self.save_message(
        thread_id=thread_id,
        sender=sender,
        recipient=recipient,
        content=content or body,
        body=body or content,
        channel=channel,
        status=status,
        metadata=metadata,
    )

  def _row_to_message(self, row: sqlite3.Row) -> ClientMessage:
    d = dict(row)
    if "metadata" in d and isinstance(d["metadata"], str):
      try:
        d["metadata"] = json.loads(d["metadata"])
      except Exception:
        d["metadata"] = {}
    return ClientMessage(**d)

  def list_messages(self, thread_id: str) -> List[ClientMessage]:
    with closing(self._get_connection()) as conn:
      cursor = conn.execute(
          "SELECT * FROM client_messages WHERE thread_id = ? ORDER BY created_at ASC",
          (thread_id,),
      )
      return [self._row_to_message(r) for r in cursor.fetchall()]

  def get_thread_messages(self, thread_id: str) -> List[ClientMessage]:
    return self.list_messages(thread_id)

  def list_recent_messages(self, limit: int = 20) -> List[ClientMessage]:
    with closing(self._get_connection()) as conn:
      cursor = conn.execute(
          "SELECT * FROM client_messages ORDER BY created_at DESC LIMIT ?",
          (limit,),
      )
      return [self._row_to_message(r) for r in cursor.fetchall()]
