"""Unit tests for DiffApplier and unified diff hunk parsing."""

from pathlib import Path
import pytest
from patching.diff_applier import DiffApplier


def test_diff_applier_apply_hunks():
  original = """def greet(name):
    print("Hello")
    return name
"""
  patch = """--- a/greet.py
+++ b/greet.py
@@ -1,3 +1,4 @@
 def greet(name):
-    print("Hello")
+    print("Hello, " + name)
+    print("Welcome!")
     return name
"""
  success, new_content, error = DiffApplier.apply_hunks_to_content(
      original, patch
  )
  assert success is True
  assert error is None
  assert 'print("Hello, " + name)' in new_content
  assert 'print("Welcome!")' in new_content


def test_diff_applier_file_backup_and_rollback(tmp_path: Path):
  test_file = tmp_path / "sample.py"
  test_file.write_text("INITIAL_STATE\n", encoding="utf-8")

  backup_map = {}
  patch = """--- a/sample.py
+++ b/sample.py
@@ -1,1 +1,1 @@
-INITIAL_STATE
+MODIFIED_STATE
"""
  success, error = DiffApplier.apply_patch_to_file(
      test_file, patch, backup_map=backup_map
  )
  assert success is True
  assert test_file.read_text(encoding="utf-8").strip() == "MODIFIED_STATE"

  # Rollback
  DiffApplier.rollback_backups(backup_map)
  assert test_file.read_text(encoding="utf-8").strip() == "INITIAL_STATE"
