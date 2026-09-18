"""Integration tests for Phase 2 write workflows, diffs, and remote approvals."""

import pytest
from app.api import create_app
from core.assistant import XerenAssistant
from fastapi.testclient import TestClient
from models.provider import MockLLMProvider
from security.permission_gate import ApprovalRequest
from tools.base import Action
from tools.registry import get_default_registry


@pytest.mark.asyncio
async def test_assistant_file_write_workflow_with_approval(test_settings):
  registry = get_default_registry(test_settings)
  # Pre-approve approvals for this integration test
  registry.permission_gate.approval_callback = lambda req: True

  assistant = XerenAssistant(settings=test_settings, tool_registry=registry)

  # Directly execute a write action via registry
  action = Action(
      action_id="act_phase2_1",
      tool_name="filesystem",
      operation="create_file",
      parameters={"path": "notes.md", "content": "# Phase 2 Implementation Notes\n"},
  )
  res = await registry.execute_action(action)

  assert res.success is True
  target_file = test_settings.workspace_root / "notes.md"
  assert target_file.exists()
  assert "Phase 2" in target_file.read_text(encoding="utf-8")


def test_api_approvals_endpoint(test_settings):
  registry = get_default_registry(test_settings)
  assistant = XerenAssistant(settings=test_settings, tool_registry=registry)
  app = create_app(assistant)
  client = TestClient(app)

  # Check approvals list
  resp = client.get("/approvals")
  assert resp.status_code == 200
  data = resp.json()
  assert "pending_approvals" in data
