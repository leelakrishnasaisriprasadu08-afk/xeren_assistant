"""Unit tests for the DAG engine, topological waves, and parameter interpolation."""

import pytest
from core.dag import (
    DAGAction,
    TaskGraph,
    CyclicDependencyError,
    ParameterResolutionError,
)
from security.policies import PermissionLevel, RiskLevel
from tools.base import ToolResult


def test_dag_topological_waves():
  """Test that actions are grouped into correct independent waves."""
  act1 = DAGAction(
      action_id="step1",
      tool_name="filesystem",
      operation="list_dir",
      parameters={},
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="List root directory",
      depends_on=[],
  )
  act2 = DAGAction(
      action_id="step2",
      tool_name="web_search",
      operation="search",
      parameters={"query": "python"},
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="Search web",
      depends_on=[],
  )
  act3 = DAGAction(
      action_id="step3",
      tool_name="filesystem",
      operation="read_file",
      parameters={"path": "main.py"},
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="Read file after listing and search",
      depends_on=["step1", "step2"],
  )

  graph = TaskGraph(actions=[act1, act2, act3])
  waves = graph.get_topological_waves()

  assert len(waves) == 2
  wave0_ids = {a.action_id for a in waves[0]}
  wave1_ids = {a.action_id for a in waves[1]}

  assert wave0_ids == {"step1", "step2"}
  assert wave1_ids == {"step3"}


def test_dag_cyclic_dependency_detection():
  """Test that cyclic dependencies raise CyclicDependencyError."""
  act1 = DAGAction(
      action_id="step1",
      tool_name="filesystem",
      operation="list_dir",
      parameters={},
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="Step 1",
      depends_on=["step2"],
  )
  act2 = DAGAction(
      action_id="step2",
      tool_name="filesystem",
      operation="read_file",
      parameters={},
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="Step 2",
      depends_on=["step1"],
  )

  graph = TaskGraph(actions=[act1, act2])
  with pytest.raises(CyclicDependencyError):
    graph.get_topological_waves()


def test_dag_missing_dependency():
  """Test that depending on a non-existent action raises ValueError."""
  act1 = DAGAction(
      action_id="step1",
      tool_name="filesystem",
      operation="list_dir",
      parameters={},
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="Step 1",
      depends_on=["non_existent_step"],
  )
  graph = TaskGraph(actions=[act1])
  with pytest.raises(ValueError, match="non-existent action"):
    graph.get_topological_waves()


def test_parameter_interpolation_exact_and_nested():
  """Test resolving upstream output parameters with dot notation and array indexing."""
  step_results = {
      "search_act": ToolResult(
          action_id="search_act",
          tool_name="web_search",
          operation="search",
          success=True,
          data={
              "results": [
                  {"title": "FastAPI Docs", "url": "https://fastapi.tiangolo.com"},
                  {"title": "Pydantic Docs", "url": "https://docs.pydantic.dev"},
              ]
          },
      ),
      "file_act": ToolResult(
          action_id="file_act",
          tool_name="filesystem",
          operation="read_file",
          success=True,
          data={"path": "src/config.py", "content": "DEBUG = True"},
      ),
  }

  # Test nested array + dict extraction
  url = TaskGraph.resolve_parameter_string("${search_act.results.0.url}", step_results)
  assert url == "https://fastapi.tiangolo.com"

  # Test composite string interpolation
  desc = TaskGraph.resolve_parameter_string(
      "Read file at ${file_act.path} with status", step_results
  )
  assert desc == "Read file at src/config.py with status"

  # Test action parameter resolution
  action = DAGAction(
      action_id="act_next",
      tool_name="filesystem",
      operation="write_file",
      parameters={
          "target_url": "${search_act.results.1.url}",
          "info": "Config was: ${file_act.content}",
      },
      required_permission=PermissionLevel.ASK,
      risk_level=RiskLevel.MEDIUM,
      reason="Write output",
      depends_on=["search_act", "file_act"],
  )

  resolved = TaskGraph.resolve_action_parameters(action, step_results)
  assert resolved["target_url"] == "https://docs.pydantic.dev"
  assert resolved["info"] == "Config was: DEBUG = True"


def test_unresolved_parameter_error():
  """Test that referencing an unexecuted upstream action raises ParameterResolutionError for exact matches."""
  step_results = {}
  with pytest.raises(ParameterResolutionError):
    TaskGraph.resolve_parameter_string("${unexecuted_act.data}", step_results)
