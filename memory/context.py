"""Session context and conversational short-term memory."""

from typing import List, Optional
from pydantic import BaseModel, Field
from models.base import LLMMessage


class ConversationContext(BaseModel):
  """Container for conversational short-term state."""

  session_id: str = "default_session"
  messages: List[LLMMessage] = Field(default_factory=list)
  active_intent: Optional[str] = None
  last_executed_tool: Optional[str] = None


class SessionMemory:
  """Manages in-memory sliding window of conversation messages."""

  def __init__(self, max_messages: int = 20):
    self.max_messages = max_messages
    self._sessions: dict[str, ConversationContext] = {}

  def get_context(self, session_id: str = "default_session") -> ConversationContext:
    if session_id not in self._sessions:
      self._sessions[session_id] = ConversationContext(session_id=session_id)
    return self._sessions[session_id]

  def add_message(self, role: str, content: str, session_id: str = "default_session") -> None:
    ctx = self.get_context(session_id)
    ctx.messages.append(LLMMessage(role=role, content=content))
    # Enforce sliding window to prevent unbounded context growth
    if len(ctx.messages) > self.max_messages:
      ctx.messages = ctx.messages[-self.max_messages:]

  def clear_session(self, session_id: str = "default_session") -> None:
    if session_id in self._sessions:
      del self._sessions[session_id]
