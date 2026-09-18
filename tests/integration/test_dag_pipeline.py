"""Integration tests for DAG Pipeline execution, multi-wave concurrency, dynamic parameter resolution, and self-healing in Controller."""

import os
import pytest
from core.controller import CancellationToken, ExecutionController
from core.dag import DAGAction, TaskGraph
from core.replanner import DynamicReplanner
from core.verifier import Verifier
from security.diff_engine import DiffEngine
from security.permission_gate import PermissionGate
from security.policies import PermissionLevel, RiskLevel
from tools.filesystem_tool import FilesystemTool
from tools.registry import ToolRegistry
from tools.sandbox import FileSandbox


@pytest.fixture
def controller_setup(tmp_path):
  """Set up execution controller with initialized tools and permission gate in test sandbox."""
  sandbox_dir = tmp_path / "sandbox"
  sandbox_dir.mkdir()
  sandbox = FileSandbox(sandbox_dir)
  gate = PermissionGate(
      workspace_root=sandbox_dir, approval_callback=lambda req: True
  )

  registry = ToolRegistry(permission_gate=gate)
  fs_tool = FilesystemTool(sandbox=sandbox)
  registry.register_tool(fs_tool)

  verifier = Verifier()
  replanner = DynamicReplanner()

  controller = ExecutionController(
      tool_registry=registry,
      verifier=verifier,
      replanner=replanner,
      max_steps=10,
      max_retries=2,
      task_timeout=30.0,
  )

  return controller, sandbox_dir


@pytest.mark.asyncio
async def test_dag_multiwave_parameter_passing(controller_setup):
  """Test executing a 2-wave DAG where Wave 2 consumes parameters dynamically from Wave 1."""
  controller, sandbox_dir = controller_setup

  act1 = DAGAction(
      action_id="act_write",
      tool_name="filesystem",
      operation="write_file",
      parameters={"path": "note.txt", "content": "Xeren Assistant Phase 3 DAG"},
      required_permission=PermissionLevel.ASK,
      risk_level=RiskLevel.MEDIUM,
      reason="Write note file",
      depends_on=[],
  )

  act2 = DAGAction(
      action_id="act_read",
      tool_name="filesystem",
      operation="read_file",
      parameters={"path": "${act_write.path}"},
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="Read note file using dynamic path from step 1",
      depends_on=["act_write"],
  )

  graph = TaskGraph(actions=[act1, act2])
  result = await controller.execute_task_graph(graph)

  assert result.success is True
  assert len(result.step_records) == 2
  assert result.step_records[0].action.action_id == "act_write"
  assert result.step_records[1].action.action_id == "act_read"

  # Verify the second step actually read the file written in step 1
  read_data = result.step_records[1].tool_result.data
  assert read_data["content"] == "Xeren Assistant Phase 3 DAG"


@pytest.mark.asyncio
async def test_dag_self_healing_recovery(controller_setup):
  """Test that when a step fails with a missing file, the controller self-heals by running a search repair."""
  controller, sandbox_dir = controller_setup

  # First create an existing file
  existing_file = sandbox_dir / "target_doc.md"
  existing_file.write_text("Found documentation content", encoding="utf-8")

  # Plan an action that attempts to read an incorrect path
  act_fail = DAGAction(
      action_id="act_bad_read",
      tool_name="filesystem",
      operation="read_file",
      parameters={"path": "missing_folder/target_doc.md"},
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="Attempt to read file at wrong path",
      depends_on=[],
  )

  graph = TaskGraph(actions=[act_fail])
  result = await controller.execute_task_graph(
      graph, user_query="Read target_doc"
  )

  assert result.success is True
  assert len(result.step_records) == 1
  record = result.step_records[0]
  assert record.was_repaired is True
  assert record.action.operation == "search_files"
  assert "target_doc" in record.action.parameters["query"]


@pytest.mark.asyncio
async def test_dag_cancellation_abort(controller_setup):
  """Test that a cancellation token aborts task graph execution between waves."""
  controller, sandbox_dir = controller_setup

  token = CancellationToken()

  act1 = DAGAction(
      action_id="step1",
      tool_name="filesystem",
      operation="write_file",
      parameters={"path": "step1.txt", "content": "data"},
      required_permission=PermissionLevel.ASK,
      risk_level=RiskLevel.MEDIUM,
      reason="Step 1",
      depends_on=[],
  )
  act2 = DAGAction(
      action_id="step2",
      tool_name="filesystem",
      operation="read_file",
      parameters={"path": "step1.txt"},
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="Step 2",
      depends_on=["step1"],
  )

  graph = TaskGraph(actions=[act1, act2])

  # Cancel before starting
  token.cancel()
  result = await controller.execute_task_graph(graph, cancellation_token=token)

  assert result.success is False
  assert result.aborted_by_cancellation is True
  assert "cancelled by user" in result.error
