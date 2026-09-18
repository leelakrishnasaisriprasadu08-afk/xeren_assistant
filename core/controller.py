"""Execution Controller managing DAG task loops, concurrent waves, bounded retries, dynamic replanning, and cancellations."""

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field
from tools.base import Action, ToolResult
from tools.registry import ToolRegistry
from .dag import DAGAction, TaskGraph
from .replanner import DynamicReplanner
from .verifier import VerificationResult, Verifier


class CancellationToken:
  """Thread-safe cancellation token allowing instant abort of running tasks."""

  def __init__(self):
    self._is_cancelled = False

  def cancel(self) -> None:
    self._is_cancelled = True

  @property
  def is_cancelled(self) -> bool:
    return self._is_cancelled


class StepExecutionRecord(BaseModel):
  """Execution record for a single step in a plan."""

  action: Action
  attempt_count: int = 1
  tool_result: Optional[ToolResult] = None
  verification_result: Optional[VerificationResult] = None
  duration_ms: float = 0.0
  success: bool = False
  error: Optional[str] = None
  was_repaired: bool = False


class ExecutionResult(BaseModel):
  """Final result of controller plan execution."""

  success: bool
  step_records: List[StepExecutionRecord] = Field(default_factory=list)
  total_duration_ms: float = 0.0
  error: Optional[str] = None
  aborted_by_cancellation: bool = False
  timed_out: bool = False
  step_results_map: Dict[str, Any] = Field(default_factory=dict)


class ExecutionController:
  """Controls concurrent DAG plan execution with safety bounds and dynamic replanning."""

  def __init__(
      self,
      tool_registry: ToolRegistry,
      verifier: Optional[Verifier] = None,
      replanner: Optional[DynamicReplanner] = None,
      max_steps: int = 10,
      max_retries: int = 2,
      task_timeout: float = 60.0,
  ):
    self.tool_registry = tool_registry
    self.verifier = verifier or Verifier()
    self.replanner = replanner or DynamicReplanner()
    self.max_steps = max_steps
    self.max_retries = max_retries
    self.task_timeout = task_timeout

  async def _execute_single_action(
      self,
      action: DAGAction,
      step_results: Dict[str, ToolResult],
      token: CancellationToken,
      user_query: str = "",
  ) -> StepExecutionRecord:
    """Executes a single action with dynamic parameter interpolation, retries, and dynamic replanning."""
    step_start = time.perf_counter()

    # 1. Resolve dynamic parameter interpolation from upstream dependencies
    resolved_params = TaskGraph.resolve_action_parameters(action, step_results)
    resolved_action = action.model_copy(update={"parameters": resolved_params})

    max_attempts = 1 + self.max_retries
    last_result: Optional[ToolResult] = None
    last_verification: Optional[VerificationResult] = None
    step_success = False
    repaired = False

    for attempt in range(1, max_attempts + 1):
      if token.is_cancelled:
        break

      last_result = await self.tool_registry.execute_action(resolved_action)
      last_verification = self.verifier.verify_action_result(
          resolved_action, last_result
      )

      if last_verification.verified:
        step_success = True
        break

      # If verification failed and we can attempt self-healing replanning
      if last_verification.is_retryable and attempt < max_attempts:
        repair_action = await self.replanner.plan_correction(
            failed_action=resolved_action,
            error_message=last_verification.feedback,
            user_query=user_query,
            prior_results=step_results,
        )
        if repair_action:
          # Execute repair action as fallback for this step
          repair_result = await self.tool_registry.execute_action(repair_action)
          repair_verif = self.verifier.verify_action_result(
              repair_action, repair_result
          )
          if repair_verif.verified:
            last_result = repair_result
            last_verification = repair_verif
            resolved_action = repair_action
            step_success = True
            repaired = True
            break

      if not last_verification.is_retryable:
        break

      await asyncio.sleep(0.2 * attempt)

    step_elapsed = (time.perf_counter() - step_start) * 1000
    return StepExecutionRecord(
        action=resolved_action,
        attempt_count=attempt,
        tool_result=last_result,
        verification_result=last_verification,
        duration_ms=step_elapsed,
        success=step_success,
        was_repaired=repaired,
        error=(
            None
            if step_success
            else (
                last_verification.feedback
                if last_verification
                else "Step failed"
            )
        ),
    )

  async def execute_task_graph(
      self,
      task_graph: TaskGraph,
      cancellation_token: Optional[CancellationToken] = None,
      on_step_progress: Optional[Callable[[StepExecutionRecord], None]] = None,
      user_query: str = "",
  ) -> ExecutionResult:
    """Executes a TaskGraph in concurrent topological waves with parameter passing."""
    start_total_time = time.perf_counter()
    step_records: List[StepExecutionRecord] = []
    step_results: Dict[str, ToolResult] = {}
    token = cancellation_token or CancellationToken()

    if len(task_graph.actions) > self.max_steps:
      elapsed = (time.perf_counter() - start_total_time) * 1000
      return ExecutionResult(
          success=False,
          error=(
              f"Plan rejected: Action count ({len(task_graph.actions)}) exceeds"
              f" max allowed steps ({self.max_steps})."
          ),
          total_duration_ms=elapsed,
      )

    waves = task_graph.get_topological_waves()

    for wave_idx, wave in enumerate(waves):
      if token.is_cancelled:
        elapsed = (time.perf_counter() - start_total_time) * 1000
        return ExecutionResult(
            success=False,
            step_records=step_records,
            aborted_by_cancellation=True,
            error="Task was cancelled by user.",
            total_duration_ms=elapsed,
        )

      current_elapsed_secs = time.perf_counter() - start_total_time
      if current_elapsed_secs >= self.task_timeout:
        return ExecutionResult(
            success=False,
            step_records=step_records,
            timed_out=True,
            error=(
                f"Overall task timed out after {self.task_timeout}s at wave"
                f" {wave_idx + 1}/{len(waves)}."
            ),
            total_duration_ms=current_elapsed_secs * 1000,
        )

      # Execute actions in current wave concurrently
      wave_tasks = [
          self._execute_single_action(
              act, step_results, token, user_query=user_query
          )
          for act in wave
      ]
      wave_records: List[StepExecutionRecord] = await asyncio.gather(
          *wave_tasks
      )

      for rec in wave_records:
        step_records.append(rec)
        if rec.tool_result:
          step_results[rec.action.action_id] = rec.tool_result

        if on_step_progress:
          try:
            on_step_progress(rec)
          except Exception:
            pass

        if not rec.success:
          elapsed = (time.perf_counter() - start_total_time) * 1000
          return ExecutionResult(
              success=False,
              step_records=step_records,
              step_results_map={
                  k: v.model_dump() for k, v in step_results.items()
              },
              error=(
                  f"Step ({rec.action.tool_name}:{rec.action.operation})"
                  f" failed: {rec.error}"
              ),
              total_duration_ms=elapsed,
          )

    total_time = (time.perf_counter() - start_total_time) * 1000
    return ExecutionResult(
        success=True,
        step_records=step_records,
        step_results_map={k: v.model_dump() for k, v in step_results.items()},
        total_duration_ms=total_time,
    )

  async def execute_plan(
      self,
      actions: List[Action],
      cancellation_token: Optional[CancellationToken] = None,
      on_step_progress: Optional[Callable[[StepExecutionRecord], None]] = None,
      user_query: str = "",
  ) -> ExecutionResult:
    """Sequential plan execution wrapper backed by TaskGraph."""
    # Convert list of actions into sequential DAG
    graph = TaskGraph()
    prev_id = None
    for act in actions:
      dag_act = DAGAction(
          action_id=act.action_id,
          tool_name=act.tool_name,
          operation=act.operation,
          parameters=act.parameters,
          required_permission=act.required_permission,
          risk_level=act.risk_level,
          reason=act.reason,
          timeout=act.timeout,
          depends_on=[prev_id] if prev_id else [],
      )
      graph.add_action(dag_act)
      prev_id = act.action_id

    return await self.execute_task_graph(
        graph,
        cancellation_token=cancellation_token,
        on_step_progress=on_step_progress,
        user_query=user_query,
    )
