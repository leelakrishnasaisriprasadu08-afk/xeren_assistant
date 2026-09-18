"""Unit tests for memory subsystem."""

from memory.context import SessionMemory
from memory.preferences import PreferencesManager, UserPreferences
from memory.storage import SQLiteSessionStorage
from models.base import LLMMessage


def test_session_memory_sliding_window():
  mem = SessionMemory(max_messages=3)
  for i in range(5):
    mem.add_message("user", f"msg_{i}")

  ctx = mem.get_context()
  assert len(ctx.messages) == 3
  assert ctx.messages[0].content == "msg_2"
  assert ctx.messages[2].content == "msg_4"


def test_sqlite_session_storage(temp_workspace):
  db_path = temp_workspace / "mem.sqlite"
  storage = SQLiteSessionStorage(db_path=db_path)

  storage.save_message("session_1", LLMMessage(role="user", content="hello"))
  storage.save_message(
      "session_1", LLMMessage(role="assistant", content="hi there")
  )

  history = storage.get_history("session_1")
  assert len(history) == 2
  assert history[0].role == "user"
  assert history[1].role == "assistant"


def test_preferences_manager(temp_workspace):
  pref_file = temp_workspace / "preferences.yaml"
  mgr = PreferencesManager(file_path=pref_file)

  prefs = UserPreferences(user_name="AlphaDeveloper", preferred_language="rust")
  mgr.save(prefs)

  # Reload
  reloaded = PreferencesManager(file_path=pref_file).preferences
  assert reloaded.user_name == "AlphaDeveloper"
  assert reloaded.preferred_language == "rust"
