"""Unit tests for CommunicationTool and ClientAgent (Phase 10)."""

import pytest
import tempfile
import os
from unittest.mock import MagicMock, patch
from tools.base import Action
from tools.communication_tool import CommunicationTool
from models.provider import MockLLMProvider
from memory.client_store import ClientStore


@pytest.fixture
def temp_db():
  with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
    db_path = f.name
  yield db_path
  if os.path.exists(db_path):
    os.remove(db_path)


@pytest.fixture
def mock_llm():
  return MockLLMProvider()


@pytest.fixture
def comm_tool(temp_db, mock_llm):
  store = ClientStore(db_path=temp_db)
  tool = CommunicationTool(client_store=store)
  tool.agent.llm_provider = mock_llm
  return tool


@pytest.mark.asyncio
async def test_create_and_get_client_profile(comm_tool):
  # Create client
  res = await comm_tool.execute(Action(
      action_id="act_create",
      tool_name="communication",
      operation="create_client",
      parameters={
          "name": "Wayne Enterprises",
          "email": "bruce@wayne.corp",
          "company": "Wayne Enterprises",
          "communication_tone": "concise",
      }
  ))
  assert res.success is True
  client_id = res.data["client_id"]

  # Get client profile
  res2 = await comm_tool.execute(Action(
      action_id="act_get",
      tool_name="communication",
      operation="get_client_profile",
      parameters={"client_id": client_id}
  ))
  assert res2.success is True
  assert res2.data["client"]["email"] == "bruce@wayne.corp"
  assert res2.data["client"]["communication_tone"] == "concise"


@pytest.mark.asyncio
async def test_draft_client_reply(comm_tool):
  # First create client
  create_res = await comm_tool.execute(Action(
      action_id="c1",
      tool_name="communication",
      operation="create_client",
      parameters={"name": "Stark Industries", "email": "tony@stark.com", "communication_tone": "technical"}
  ))
  client_id = create_res.data["client_id"]

  # Draft reply
  draft_res = await comm_tool.execute(Action(
      action_id="d1",
      tool_name="communication",
      operation="draft_client_reply",
      parameters={
          "client_id": client_id,
          "incoming_message": "Can you provide an update on the quantum reactor telemetry API?",
          "task_context": "Refactored telemetry pipeline and fixed timestamp parser.",
          "include_git_status": False,
      }
  ))
  assert draft_res.success is True
  assert "draft" in draft_res.data
  draft = draft_res.data["draft"]
  assert draft["recipient"] == "tony@stark.com"
  assert draft["style"] == "technical"
  assert len(draft["body"]) > 0
  assert draft["confidence_score"] >= 0.8


@pytest.mark.asyncio
async def test_send_email_and_thread_listing(comm_tool):
  send_res = await comm_tool.execute(Action(
      action_id="s1",
      tool_name="communication",
      operation="send_email",
      parameters={
          "to": "partner@global.com",
          "subject": "Phase 10 Release Notification",
          "body": "The client subsystem is operational and passes all security gates.",
      }
  ))
  assert send_res.success is True
  assert send_res.data["to"] == "partner@global.com"
  assert "thread_id" in send_res.data
  assert "message_id" in send_res.data

  # List threads
  list_res = await comm_tool.execute(Action(
      action_id="l1",
      tool_name="communication",
      operation="list_client_threads",
      parameters={}
  ))
  assert list_res.success is True
  assert len(list_res.data["threads"]) >= 1


@pytest.mark.asyncio
async def test_send_webhook(comm_tool):
  with patch("urllib.request.urlopen") as mock_urlopen:
    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = b'{"status": "received"}'
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    res = await comm_tool.execute(Action(
        action_id="w1",
        tool_name="communication",
        operation="send_webhook",
        parameters={
            "url": "https://api.example.com/webhook",
            "payload": {"event": "deployment_success", "build": 104},
        }
    ))
    assert res.success is True
    assert res.data["status_code"] == 200
    assert res.data["url"] == "https://api.example.com/webhook"


@pytest.mark.asyncio
async def test_unknown_operation(comm_tool):
  res = await comm_tool.execute(Action(
      action_id="u1",
      tool_name="communication",
      operation="teleport_message",
      parameters={}
  ))
  assert res.success is False
  assert "Unsupported operation" in res.error
