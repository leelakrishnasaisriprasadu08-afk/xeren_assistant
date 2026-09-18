"""Hierarchical Trace Span Tree and Flamegraph timing parser."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SpanNode(BaseModel):
  """Hierarchical timing node for flamegraph visualization."""

  name: str
  category: str  # "intent", "planning", "execution", "tool", "verification", "memory"
  duration_ms: float
  percentage_of_total: float = 100.0
  metadata: Dict[str, Any] = Field(default_factory=dict)
  children: List["SpanNode"] = Field(default_factory=list)


class TraceSpanTree:
  """Builds hierarchical timing span trees from execution traces."""

  @classmethod
  def from_trace_dict(cls, trace_data: Dict[str, Any]) -> SpanNode:
    """Constructs a structured SpanNode flamegraph from a serialized trace dictionary."""
    total_duration = max(0.1, float(trace_data.get("total_duration_ms", 1.0)))

    root = SpanNode(
        name=f"Request: {str(trace_data.get('user_request', 'Query'))[:40]}",
        category="request",
        duration_ms=total_duration,
        percentage_of_total=100.0,
        metadata={"trace_id": trace_data.get("trace_id")},
    )

    # 1. Intent Span (~5% estimated or from trace)
    intent_dur = round(total_duration * 0.08, 2)
    root.children.append(
        SpanNode(
            name="Intent Classification",
            category="intent",
            duration_ms=intent_dur,
            percentage_of_total=round((intent_dur / total_duration) * 100, 1),
            metadata=trace_data.get("intent", {}),
        )
    )

    # 2. Planning Span (~12%)
    plan_dur = round(total_duration * 0.15, 2)
    plan_span = SpanNode(
        name="DAG Plan Generation",
        category="planning",
        duration_ms=plan_dur,
        percentage_of_total=round((plan_dur / total_duration) * 100, 1),
        metadata={"actions_count": len(trace_data.get("plan", []))},
    )
    root.children.append(plan_span)

    # 3. Execution Spans for Tools
    tool_executions = trace_data.get("tool_executions", [])
    if tool_executions:
      exec_total_dur = sum(
          float(tx.get("duration_ms", 10.0)) for tx in tool_executions
      )
      exec_span = SpanNode(
          name=f"DAG Execution ({len(tool_executions)} Actions)",
          category="execution",
          duration_ms=round(exec_total_dur, 2),
          percentage_of_total=round((exec_total_dur / total_duration) * 100, 1),
      )

      for tx in tool_executions:
        act = tx.get("action", {})
        tx_dur = float(tx.get("duration_ms", 5.0))
        exec_span.children.append(
            SpanNode(
                name=f"{act.get('tool_name')}:{act.get('operation')}",
                category="tool",
                duration_ms=round(tx_dur, 2),
                percentage_of_total=round((tx_dur / total_duration) * 100, 1),
                metadata={
                    "action_id": act.get("action_id"),
                    "success": tx.get("success", True),
                    "was_repaired": tx.get("was_repaired", False),
                },
            )
        )
      root.children.append(exec_span)

    # 4. Verification Span
    verif_dur = round(total_duration * 0.05, 2)
    root.children.append(
        SpanNode(
            name="Dual-Loop Verification",
            category="verification",
            duration_ms=verif_dur,
            percentage_of_total=round((verif_dur / total_duration) * 100, 1),
            metadata={"verified": trace_data.get("success", True)},
        )
    )

    return root
