"""Unit tests for TraceSpanTree flamegraph latency tree builder."""

import pytest
from telemetry.flamegraph import TraceSpanTree


def test_trace_span_tree_hierarchy():
  """Test parsing a raw trace dictionary into a hierarchical flamegraph tree."""
  mock_trace = {
      "trace_id": "trace-12345",
      "user_request": "Inspect git repo and summarize issues",
      "total_duration_ms": 1200.0,
      "success": True,
      "intent": {"intent_type": "GITHUB"},
      "plan": [
          {"action_id": "act_01", "tool_name": "github", "operation": "read_issues"}
      ],
      "tool_executions": [
          {
              "action": {"action_id": "act_01", "tool_name": "github", "operation": "read_issues"},
              "duration_ms": 850.0,
              "success": True,
              "was_repaired": False,
          }
      ],
  }

  tree = TraceSpanTree.from_trace_dict(mock_trace)

  assert tree.name.startswith("Request: Inspect git repo")
  assert tree.duration_ms == 1200.0
  assert tree.percentage_of_total == 100.0
  assert len(tree.children) >= 3

  # Verify tool execution span
  exec_span = next(c for c in tree.children if c.category == "execution")
  assert exec_span.duration_ms == 850.0
  assert len(exec_span.children) == 1
  assert exec_span.children[0].name == "github:read_issues"
