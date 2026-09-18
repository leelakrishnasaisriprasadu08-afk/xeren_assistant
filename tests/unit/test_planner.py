"""Unit tests for TaskPlanner."""

import pytest
from core.intent import Intent, IntentType
from core.planner import TaskPlanner
from security.policies import PermissionLevel, RiskLevel


@pytest.mark.asyncio
async def test_planner_generates_strict_action_schema():
  planner = TaskPlanner()

  # Filesystem plan
  intent = Intent(intent_type=IntentType.FILESYSTEM)
  actions = await planner.plan("read file README.md", intent)
  assert len(actions) == 1
  act = actions[0]

  assert act.action_id == "act_01"
  assert act.tool_name == "filesystem"
  assert act.operation == "read_file"
  assert act.parameters == {"path": "README.md"}
  assert act.required_permission == PermissionLevel.ALLOWED
  assert act.risk_level == RiskLevel.LOW
  assert act.timeout > 0


@pytest.mark.asyncio
async def test_composite_workflow_plan():
  planner = TaskPlanner()
  intent = Intent(
      intent_type=IntentType.COMPOSITE, entities={"repo": "owner/repo"}
  )
  actions = await planner.plan(
      "check issues in owner/repo and create a task for reviewing them", intent
  )

  assert len(actions) == 2
  assert actions[0].tool_name == "github"
  assert actions[0].operation == "read_issues"
  assert actions[1].tool_name == "tasks"
  assert actions[1].operation == "create_task"
