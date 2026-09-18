"""Operation-level security policies and permission definitions."""

from enum import Enum
from typing import Dict, Tuple
from pydantic import BaseModel, Field


class PermissionLevel(str, Enum):
  ALLOWED = "ALLOWED"
  ASK = "ASK"
  DENIED = "DENIED"


class RiskLevel(str, Enum):
  LOW = "LOW"
  MEDIUM = "MEDIUM"
  HIGH = "HIGH"
  CRITICAL = "CRITICAL"


class OperationPolicy(BaseModel):
  """Security policy definition for an individual tool operation."""

  tool_name: str
  operation: str
  permission_level: PermissionLevel
  risk_level: RiskLevel
  description: str
  requires_user_approval: bool = False
  is_blocked: bool = False


# Frozen Phase-1 Policy Matrix per operation
OPERATION_POLICIES: Dict[Tuple[str, str], OperationPolicy] = {
    # Filesystem operations
    ("filesystem", "read_file"): OperationPolicy(
        tool_name="filesystem",
        operation="read_file",
        permission_level=PermissionLevel.ALLOWED,
        risk_level=RiskLevel.LOW,
        description="Read file contents within workspace root",
    ),
    ("filesystem", "list_dir"): OperationPolicy(
        tool_name="filesystem",
        operation="list_dir",
        permission_level=PermissionLevel.ALLOWED,
        risk_level=RiskLevel.LOW,
        description="List files and directories in workspace",
    ),
    ("filesystem", "search_files"): OperationPolicy(
        tool_name="filesystem",
        operation="search_files",
        permission_level=PermissionLevel.ALLOWED,
        risk_level=RiskLevel.LOW,
        description="Search for file names or contents in workspace",
    ),
    ("filesystem", "write_file"): OperationPolicy(
        tool_name="filesystem",
        operation="write_file",
        permission_level=PermissionLevel.ASK,
        risk_level=RiskLevel.MEDIUM,
        description="Write or overwrite a file in workspace",
        requires_user_approval=True,
    ),
    ("filesystem", "create_file"): OperationPolicy(
        tool_name="filesystem",
        operation="create_file",
        permission_level=PermissionLevel.ASK,
        risk_level=RiskLevel.MEDIUM,
        description="Create a new file in workspace",
        requires_user_approval=True,
    ),
    ("filesystem", "delete_file"): OperationPolicy(
        tool_name="filesystem",
        operation="delete_file",
        permission_level=PermissionLevel.DENIED,
        risk_level=RiskLevel.CRITICAL,
        description="Delete a file from disk (Blocked in Phase 1)",
        is_blocked=True,
    ),
    ("filesystem", "remove_dir"): OperationPolicy(
        tool_name="filesystem",
        operation="remove_dir",
        permission_level=PermissionLevel.DENIED,
        risk_level=RiskLevel.CRITICAL,
        description="Remove a directory (Blocked in Phase 1)",
        is_blocked=True,
    ),
    # GitHub operations
    ("github", "get_repo"): OperationPolicy(
        tool_name="github",
        operation="get_repo",
        permission_level=PermissionLevel.ALLOWED,
        risk_level=RiskLevel.LOW,
        description="Fetch repository metadata",
    ),
    ("github", "read_issues"): OperationPolicy(
        tool_name="github",
        operation="read_issues",
        permission_level=PermissionLevel.ALLOWED,
        risk_level=RiskLevel.LOW,
        description="Read issues from repository",
    ),
    ("github", "read_prs"): OperationPolicy(
        tool_name="github",
        operation="read_prs",
        permission_level=PermissionLevel.ALLOWED,
        risk_level=RiskLevel.LOW,
        description="Read pull requests from repository",
    ),
    ("github", "get_commits"): OperationPolicy(
        tool_name="github",
        operation="get_commits",
        permission_level=PermissionLevel.ALLOWED,
        risk_level=RiskLevel.LOW,
        description="Read commit logs from repository",
    ),
    ("github", "create_issue"): OperationPolicy(
        tool_name="github",
        operation="create_issue",
        permission_level=PermissionLevel.ASK,
        risk_level=RiskLevel.HIGH,
        description="Create a new issue on GitHub",
        requires_user_approval=True,
    ),
    ("github", "create_pr"): OperationPolicy(
        tool_name="github",
        operation="create_pr",
        permission_level=PermissionLevel.ASK,
        risk_level=RiskLevel.HIGH,
        description="Open a new pull request on GitHub",
        requires_user_approval=True,
    ),
    ("github", "push_code"): OperationPolicy(
        tool_name="github",
        operation="push_code",
        permission_level=PermissionLevel.ASK,
        risk_level=RiskLevel.HIGH,
        description="Push commits to GitHub branch",
        requires_user_approval=True,
    ),
    # Local SQLite Task operations
    ("tasks", "create_task"): OperationPolicy(
        tool_name="tasks",
        operation="create_task",
        permission_level=PermissionLevel.ALLOWED,
        risk_level=RiskLevel.LOW,
        description="Create a task in local storage",
    ),
    ("tasks", "list_tasks"): OperationPolicy(
        tool_name="tasks",
        operation="list_tasks",
        permission_level=PermissionLevel.ALLOWED,
        risk_level=RiskLevel.LOW,
        description="List tasks from local storage",
    ),
    ("tasks", "update_task"): OperationPolicy(
        tool_name="tasks",
        operation="update_task",
        permission_level=PermissionLevel.ALLOWED,
        risk_level=RiskLevel.LOW,
        description="Update task status or details",
    ),
    ("tasks", "get_task"): OperationPolicy(
        tool_name="tasks",
        operation="get_task",
        permission_level=PermissionLevel.ALLOWED,
        risk_level=RiskLevel.LOW,
        description="Get specific task details",
    ),
    ("tasks", "delete_task"): OperationPolicy(
        tool_name="tasks",
        operation="delete_task",
        permission_level=PermissionLevel.ASK,
        risk_level=RiskLevel.MEDIUM,
        description="Delete a task from local storage",
        requires_user_approval=True,
    ),
    # Web search operations
    ("web_search", "search"): OperationPolicy(
        tool_name="web_search",
        operation="search",
        permission_level=PermissionLevel.ALLOWED,
        risk_level=RiskLevel.LOW,
        description="Search the web for query terms",
    ),
    ("web_search", "fetch_page"): OperationPolicy(
        tool_name="web_search",
        operation="fetch_page",
        permission_level=PermissionLevel.ALLOWED,
        risk_level=RiskLevel.LOW,
        description="Fetch content from public web URL",
    ),
    # Shell execution operations
    ("shell", "execute_command"): OperationPolicy(
        tool_name="shell",
        operation="execute_command",
        permission_level=PermissionLevel.ASK,
        risk_level=RiskLevel.HIGH,
        description="Execute a shell command within the workspace sandbox",
        requires_user_approval=True,
    ),
    # Generic HTTP operations
    ("http", "get"): OperationPolicy(
        tool_name="http",
        operation="get",
        permission_level=PermissionLevel.ALLOWED,
        risk_level=RiskLevel.LOW,
        description="Perform an HTTP GET request to a remote endpoint",
    ),
    ("http", "post"): OperationPolicy(
        tool_name="http",
        operation="post",
        permission_level=PermissionLevel.ASK,
        risk_level=RiskLevel.MEDIUM,
        description="Perform an HTTP POST request to a remote endpoint",
        requires_user_approval=True,
    ),
    ("http", "put"): OperationPolicy(
        tool_name="http",
        operation="put",
        permission_level=PermissionLevel.ASK,
        risk_level=RiskLevel.MEDIUM,
        description="Perform an HTTP PUT request to a remote endpoint",
        requires_user_approval=True,
    ),
    ("http", "delete"): OperationPolicy(
        tool_name="http",
        operation="delete",
        permission_level=PermissionLevel.ASK,
        risk_level=RiskLevel.HIGH,
        description="Perform an HTTP DELETE request to a remote endpoint",
        requires_user_approval=True,
    ),
    # Subagent delegation operations
    ("subagent", "delegate_research"): OperationPolicy(
        tool_name="subagent",
        operation="delegate_research",
        permission_level=PermissionLevel.ALLOWED,
        risk_level=RiskLevel.LOW,
        description="Delegate autonomous multi-source deep research to ResearchSubagent",
    ),
    ("subagent", "delegate_code_review"): OperationPolicy(
        tool_name="subagent",
        operation="delegate_code_review",
        permission_level=PermissionLevel.ALLOWED,
        risk_level=RiskLevel.LOW,
        description="Delegate code and diff security analysis to CodeReviewerSubagent",
    ),
}


def get_operation_policy(tool_name: str, operation: str) -> OperationPolicy:
  """Look up the security policy for a tool operation.

  Defaults to DENIED for any unregistered operation.
  """
  key = (tool_name.lower(), operation.lower())
  if key in OPERATION_POLICIES:
    return OPERATION_POLICIES[key]

  # Default secure fallback for unknown operations
  return OperationPolicy(
      tool_name=tool_name,
      operation=operation,
      permission_level=PermissionLevel.DENIED,
      risk_level=RiskLevel.CRITICAL,
      description=f"Unrecognized operation '{operation}' on tool '{tool_name}'",
      is_blocked=True,
  )
