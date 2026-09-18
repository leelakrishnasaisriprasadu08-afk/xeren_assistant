"""Directed Acyclic Graph (DAG) Task Planning and Parameter Interpolation Engine."""

from collections import defaultdict, deque
import re
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field
from security.policies import PermissionLevel, RiskLevel
from tools.base import Action, ToolResult


class CyclicDependencyError(Exception):
  """Raised when a cycle is detected in task dependencies."""

  pass


class ParameterResolutionError(Exception):
  """Raised when an upstream parameter reference cannot be resolved."""

  pass


class DAGAction(Action):
  """Action node in a DAG execution graph declaring upstream dependencies."""

  depends_on: List[str] = Field(
      default_factory=list,
      description="List of action_ids this action depends upon",
  )


class TaskGraph(BaseModel):
  """Directed Acyclic Graph representing a multi-step task execution plan."""

  actions: List[DAGAction] = Field(default_factory=list)

  def add_action(self, action: DAGAction) -> None:
    self.actions.append(action)

  def get_action_map(self) -> Dict[str, DAGAction]:
    return {act.action_id: act for act in self.actions}

  def get_topological_waves(self) -> List[List[DAGAction]]:
    """Sorts actions into parallel execution waves using Kahn's topological sort.

    Actions in the same wave have zero inter-dependencies and can run
    concurrently.
    """
    action_map = self.get_action_map()
    in_degree: Dict[str, int] = {act.action_id: 0 for act in self.actions}
    graph: Dict[str, List[str]] = defaultdict(list)

    # Build dependency graph
    for act in self.actions:
      for dep_id in act.depends_on:
        if dep_id not in action_map:
          raise ValueError(
              f"Action '{act.action_id}' depends on non-existent action"
              f" '{dep_id}'"
          )
        graph[dep_id].append(act.action_id)
        in_degree[act.action_id] += 1

    # Find nodes with 0 in-degree (initial wave)
    current_wave_ids = [
        act_id for act_id, deg in in_degree.items() if deg == 0
    ]
    waves: List[List[DAGAction]] = []
    visited_count = 0

    while current_wave_ids:
      current_wave = [action_map[aid] for aid in current_wave_ids]
      waves.append(current_wave)
      visited_count += len(current_wave_ids)

      next_wave_ids = []
      for aid in current_wave_ids:
        for neighbor in graph[aid]:
          in_degree[neighbor] -= 1
          if in_degree[neighbor] == 0:
            next_wave_ids.append(neighbor)

      current_wave_ids = next_wave_ids

    if visited_count != len(self.actions):
      raise CyclicDependencyError(
          "Cyclic dependency detected in task plan graph."
      )

    return waves

  @staticmethod
  def _resolve_json_path(data: Any, path: str) -> Any:
    """Extracts nested value using dot notation and array index (e.g.

    'data.matches.0').
    """
    current = data
    parts = path.split(".")
    for part in parts:
      if current is None:
        return None
      if isinstance(current, dict):
        current = current.get(part)
      elif isinstance(current, list):
        try:
          idx = int(part)
          current = current[idx] if 0 <= idx < len(current) else None
        except ValueError:
          return None
      else:
        return None
    return current

  @classmethod
  def resolve_parameter_string(
      cls, param_val: str, step_results: Dict[str, ToolResult]
  ) -> Any:
    """Interpolates ${act_id.field.subfield} references with actual values from step_results."""
    pattern = re.compile(r"\$\{([a-zA-Z0-9_-]+)\.([a-zA-Z0-9_.-]+)\}")

    # Check for exact whole-string match (allows returning dicts/lists without string conversion)
    exact_match = pattern.fullmatch(param_val.strip())
    if exact_match:
      act_id, path = exact_match.groups()
      if act_id not in step_results:
        raise ParameterResolutionError(
            f"Cannot resolve parameter: Upstream action '{act_id}' has not"
            " executed."
        )
      res = step_results[act_id]
      source_obj = (
          res.data if path.startswith("data.") or not hasattr(res, path) else res
      )
      resolved = cls._resolve_json_path(
          res.data if not path.startswith("data") else res.model_dump(), path
      )
      if resolved is None:
        # Try resolving directly on data
        resolved = cls._resolve_json_path(res.data, path)
      return resolved

    # Text interpolation for composite strings
    def _repl(match):
      act_id, path = match.groups()
      if act_id not in step_results:
        return f"[UNRESOLVED:{act_id}]"
      val = cls._resolve_json_path(step_results[act_id].data, path)
      return str(val) if val is not None else ""

    return pattern.sub(_repl, param_val)

  @classmethod
  def resolve_action_parameters(
      cls, action: DAGAction, step_results: Dict[str, ToolResult]
  ) -> Dict[str, Any]:
    """Recursively resolves all dynamic parameter references in an action."""
    resolved_params = {}
    for key, val in action.parameters.items():
      if isinstance(val, str):
        resolved_params[key] = cls.resolve_parameter_string(val, step_results)
      elif isinstance(val, dict):
        resolved_params[key] = {
            k: (
                cls.resolve_parameter_string(v, step_results)
                if isinstance(v, str)
                else v
            )
            for k, v in val.items()
        }
      else:
        resolved_params[key] = val
    return resolved_params
