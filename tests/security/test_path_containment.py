"""Security tests for deterministic filesystem path containment."""

from pathlib import Path
import pytest
from security.permission_gate import PathContainmentError, PermissionGate


def test_valid_in_sandbox_paths(temp_workspace):
  gate = PermissionGate(workspace_root=temp_workspace)

  # Direct child
  resolved = gate.validate_path("README.md")
  assert resolved == temp_workspace / "README.md"
  assert resolved.exists()

  # Nested subdirectory path
  resolved_nested = gate.validate_path("src/main.py")
  assert resolved_nested == temp_workspace / "src" / "main.py"
  assert resolved_nested.exists()

  # Absolute path inside sandbox
  abs_path = temp_workspace / "README.md"
  resolved_abs = gate.validate_path(abs_path)
  assert resolved_abs == abs_path


def test_path_traversal_attempts_blocked(temp_workspace):
  gate = PermissionGate(workspace_root=temp_workspace)

  # Parent directory traversal
  with pytest.raises(PathContainmentError):
    gate.validate_path("../outside.txt")

  # Deep parent traversal
  with pytest.raises(PathContainmentError):
    gate.validate_path("../../etc/passwd")

  # Windows system paths outside workspace
  with pytest.raises(PathContainmentError):
    gate.validate_path("C:/Windows/System32/cmd.exe")


def test_null_byte_injection_blocked(temp_workspace):
  gate = PermissionGate(workspace_root=temp_workspace)

  with pytest.raises(PathContainmentError, match="Null byte"):
    gate.validate_path("README.md\x00.exe")


def test_empty_path_blocked(temp_workspace):
  gate = PermissionGate(workspace_root=temp_workspace)

  with pytest.raises(PathContainmentError, match="empty"):
    gate.validate_path("")
