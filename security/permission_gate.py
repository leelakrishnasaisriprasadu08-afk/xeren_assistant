"""Permission Gatekeeper enforcing Phase 1 & 2 security policies, path containment, and interactive approvals."""

import asyncio
from datetime import datetime, timezone
import inspect
import os
from pathlib import Path
import uuid
from typing import Any, Callable, Dict, Optional, Union
from pydantic import BaseModel, Field
from .diff_engine import DiffEngine
from .policies import OperationPolicy, PermissionLevel, RiskLevel, get_operation_policy


class PermissionDeniedError(Exception):
  """Raised when an operation is blocked by security policy."""

  pass


class PathContainmentError(PermissionDeniedError):
  """Raised when a file path escapes the configured workspace sandbox."""

  pass


class ApprovalRequest(BaseModel):
  """Interactive approval request for operations requiring user confirmation (ASK)."""

  approval_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
  tool_name: str
  operation: str
  permission_level: PermissionLevel
  risk_level: RiskLevel
  description: str
  parameters: Dict[str, Any] = Field(default_factory=dict)
  diff_preview: Optional[str] = None
  change_summary: Optional[Dict[str, Any]] = None
  created_at: str = Field(
      default_factory=lambda: datetime.now(timezone.utc).isoformat()
  )


class PermissionGate:
  """Evaluates actions against security policies, workspace containment constraints, and interactive approval gates."""

  def __init__(
      self,
      workspace_root: Optional[Path] = None,
      approval_callback: Optional[
          Union[
              Callable[[ApprovalRequest], bool],
              Callable[[ApprovalRequest], Any],
          ]
      ] = None,
  ):
    self.workspace_root = (workspace_root or Path(".").resolve()).resolve()
    self.approval_callback = approval_callback

  def validate_path(self, target_path: str | Path) -> Path:
    """Deterministically validates that target_path resides inside the workspace sandbox.

    Blocks traversal attacks (../, symlink escapes, absolute drive paths).
    """
    if not target_path:
      raise PathContainmentError("Path cannot be empty.")

    raw_path_str = str(target_path)

    # Check for null bytes
    if "\x00" in raw_path_str:
      raise PathContainmentError("Null byte detected in file path.")

    # Convert to Path object
    raw_path = Path(raw_path_str)

    # Resolve absolute canonical path
    if raw_path.is_absolute():
      resolved_target = raw_path.resolve()
    else:
      resolved_target = (self.workspace_root / raw_path).resolve()

    # Check path containment
    try:
      resolved_target.relative_to(self.workspace_root)
    except ValueError:
      raise PathContainmentError(
          f"Access Denied: Path '{raw_path_str}' resolves outside workspace sandbox '{self.workspace_root}'."
      )

    return resolved_target

  def _build_approval_request(
      self,
      tool_name: str,
      operation: str,
      policy: OperationPolicy,
      parameters: Optional[Dict[str, Any]] = None,
  ) -> ApprovalRequest:
    params = parameters or {}
    diff_preview = None
    change_summary = None

    # If it's a file write/creation, generate visual diff & summary preview
    if tool_name.lower() == "filesystem" and operation.lower() in [
        "write_file",
        "create_file",
    ]:
      rel_path = params.get("path") or params.get("file_path")
      new_content = params.get("content", "")
      if rel_path:
        try:
          resolved_file = self.validate_path(rel_path)
          old_content = (
              resolved_file.read_text(encoding="utf-8", errors="replace")
              if resolved_file.exists()
              else ""
          )
          diff_preview = DiffEngine.generate_unified_diff(
              old_content, new_content, file_path=str(rel_path)
          )
          change_summary = DiffEngine.summarize_change(
              old_content, new_content
          )
        except Exception:
          diff_preview = f"(New file creation with {len(new_content)} characters)"

    return ApprovalRequest(
        tool_name=tool_name,
        operation=operation,
        permission_level=policy.permission_level,
        risk_level=policy.risk_level,
        description=policy.description,
        parameters=params,
        diff_preview=diff_preview,
        change_summary=change_summary,
    )

  async def evaluate_permission_async(
      self,
      tool_name: str,
      operation: str,
      parameters: Optional[Dict[str, Any]] = None,
  ) -> OperationPolicy:
    """Asynchronously evaluates security policy, enforcing path containment and interactive approvals."""
    policy = get_operation_policy(tool_name, operation)

    # Enforce filesystem path containment
    if tool_name.lower() == "filesystem" and parameters:
      for key in ["path", "file_path", "directory", "target_path"]:
        if key in parameters and parameters[key]:
          self.validate_path(parameters[key])

    # Enforce DENIED policies
    if (
        policy.permission_level == PermissionLevel.DENIED
        or policy.risk_level == RiskLevel.CRITICAL
    ):
      raise PermissionDeniedError(
          f"Operation '{operation}' on tool '{tool_name}' is DENIED by security policy: {policy.description}"
      )

    # Enforce ASK policies (Requires interactive approval)
    if policy.permission_level == PermissionLevel.ASK:
      approved = False
      if self.approval_callback:
        req = self._build_approval_request(
            tool_name, operation, policy, parameters
        )
        if inspect.iscoroutinefunction(self.approval_callback):
          approved = await self.approval_callback(req)
        else:
          approved = self.approval_callback(req)

      if not approved:
        raise PermissionDeniedError(
            f"Operation '{operation}' on tool '{tool_name}' requires approval (ASK) and was rejected or unconfirmed."
        )

    return policy

  def evaluate_permission(
      self,
      tool_name: str,
      operation: str,
      parameters: Optional[Dict[str, Any]] = None,
  ) -> OperationPolicy:
    """Synchronous permission evaluation helper for synchronous callers."""
    policy = get_operation_policy(tool_name, operation)

    if tool_name.lower() == "filesystem" and parameters:
      for key in ["path", "file_path", "directory", "target_path"]:
        if key in parameters and parameters[key]:
          self.validate_path(parameters[key])

    if (
        policy.permission_level == PermissionLevel.DENIED
        or policy.risk_level == RiskLevel.CRITICAL
    ):
      raise PermissionDeniedError(
          f"Operation '{operation}' on tool '{tool_name}' is DENIED by security policy: {policy.description}"
      )

    if policy.permission_level == PermissionLevel.ASK:
      approved = False
      if self.approval_callback:
        req = self._build_approval_request(
            tool_name, operation, policy, parameters
        )
        if inspect.iscoroutinefunction(self.approval_callback):
          # In sync context, cannot await; assume False unless already handled
          approved = False
        else:
          approved = self.approval_callback(req)

      if not approved:
        raise PermissionDeniedError(
            f"Operation '{operation}' on tool '{tool_name}' requires approval (ASK) and was not confirmed."
        )

    return policy
