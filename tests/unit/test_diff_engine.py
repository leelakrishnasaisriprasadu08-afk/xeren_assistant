"""Unit tests for DiffEngine."""

from security.diff_engine import DiffEngine


def test_diff_engine_generates_valid_unified_diff():
  old = "def hello():\n    return 'world'\n"
  new = "def hello():\n    return 'xeren'\n"

  diff = DiffEngine.generate_unified_diff(old, new, "test.py")

  assert "--- a/test.py" in diff
  assert "+++ b/test.py" in diff
  assert "-    return 'world'" in diff
  assert "+    return 'xeren'" in diff


def test_diff_engine_summarize_change():
  old = "line 1\nline 2\n"
  new = "line 1\nline 2 modified\nline 3 added\n"

  summary = DiffEngine.summarize_change(old, new)

  assert summary["lines_added"] >= 2
  assert summary["lines_removed"] >= 1
  assert summary["delta_bytes"] > 0
  assert summary["is_new_file"] is False


def test_diff_engine_new_file():
  summary = DiffEngine.summarize_change("", "hello xeren")
  assert summary["is_new_file"] is True
  assert summary["old_size_bytes"] == 0
  assert summary["new_size_bytes"] == len("hello xeren")
