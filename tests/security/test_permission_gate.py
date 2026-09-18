"""Security tests for operation permission gate and policy enforcement."""

import pytest
from security.permission_gate import (
    PathContainmentError,
    PermissionDeniedError,
    PermissionGate,
)
from security.policies import PermissionLevel, RiskLevel


def test_allowed_operations_pass(permission_gate):
  # Allowed read file
  policy = permission_gate.evaluate_permission(
      "filesystem", "read_file", {"path": "README.md"}
  )
  assert policy.permission_level == PermissionLevel.ALLOWED
  assert policy.risk_level == RiskLevel.LOW

  # Allowed GitHub read
  policy = permission_gate.evaluate_permission("github", "read_issues")
  assert policy.permission_level == PermissionLevel.ALLOWED

  # Allowed Web search
  policy = permission_gate.evaluate_permission("web_search", "search")
  assert policy.permission_level == PermissionLevel.ALLOWED

  # Allowed Task create
  policy = permission_gate.evaluate_permission("tasks", "create_task")
  assert policy.permission_level == PermissionLevel.ALLOWED


def test_denied_operations_blocked_strictly(permission_gate):
  # File deletion MUST be blocked in Phase 1
  with pytest.raises(PermissionDeniedError, match="DENIED"):
    permission_gate.evaluate_permission("filesystem", "delete_file")

  # Directory removal MUST be blocked
  with pytest.raises(PermissionDeniedError, match="DENIED"):
    permission_gate.evaluate_permission("filesystem", "remove_dir")

  # Unknown/unregistered operation MUST be blocked
  with pytest.raises(PermissionDeniedError, match="DENIED"):
    permission_gate.evaluate_permission("arbitrary_tool", "execute_shell")


def test_ask_operations_with_and_without_approval(temp_workspace):
  # Gate with no approval callback -> ASK operations fail
  gate_no_approval = PermissionGate(workspace_root=temp_workspace)
  with pytest.raises(PermissionDeniedError, match="requires approval"):
    gate_no_approval.evaluate_permission("filesystem", "write_file")

  with pytest.raises(PermissionDeniedError, match="requires approval"):
    gate_no_approval.evaluate_permission("github", "create_pr")

  with pytest.raises(PermissionDeniedError, match="requires approval"):
    gate_no_approval.evaluate_permission("tasks", "delete_task")

  # Gate with approval callback returning True -> passes
  gate_approved = PermissionGate(
      workspace_root=temp_workspace, approval_callback=lambda req: True
  )
  policy = gate_approved.evaluate_permission("filesystem", "write_file")
  assert policy.permission_level == PermissionLevel.ASK

  # Gate with approval callback returning False -> fails
  gate_rejected = PermissionGate(
      workspace_root=temp_workspace, approval_callback=lambda req: False
  )
  with pytest.raises(PermissionDeniedError, match="requires approval"):
    gate_rejected.evaluate_permission("github", "push_code")
