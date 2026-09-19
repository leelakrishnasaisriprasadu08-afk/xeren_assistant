"""Integration tests for Phase 10: Client Communication Subsystem and Automated Response Agent."""

import pytest
import tempfile
import os
from fastapi.testclient import TestClient
from core.assistant import XerenAssistant
from core.intent import IntentType
from memory.client_store import ClientStore
from tools.communication_tool import CommunicationTool
from models.provider import MockLLMProvider
from app.api import create_app


@pytest.fixture
def temp_env():
  with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
    db_path = f.name
  yield db_path
  if os.path.exists(db_path):
    os.remove(db_path)


@pytest.fixture
def assistant(temp_env):
  mock_llm = MockLLMProvider()
  ast = XerenAssistant(llm_provider=mock_llm)
  # Override communication tool client store to use temp db
  store = ClientStore(db_path=temp_env)
  comm_tool = CommunicationTool(client_store=store)
  comm_tool.agent.llm_provider = mock_llm
  ast.tool_registry.register_tool(comm_tool)
  return ast


@pytest.mark.asyncio
async def test_end_to_end_client_reply_drafting(assistant):
  query = "Draft a reply to client about project progress on the latest feature build"
  intent = await assistant.intent_classifier.classify(query)
  assert intent.intent_type == IntentType.CLIENT

  resp = await assistant.process_request(query)
  assert resp.success is True
  assert "Client Reply Drafted" in resp.response_text or "communication" in resp.tools_used
  assert resp.trace_id is not None


@pytest.mark.asyncio
async def test_api_client_endpoints(assistant):
  app = create_app(assistant)
  client = TestClient(app)

  # 1. Create client
  create_res = client.post("/client/create", json={
      "name": "Global Corp",
      "email": "contact@global.corp",
      "company": "Global Corp International",
      "communication_tone": "professional",
      "notes": "Key partner",
  })
  assert create_res.status_code == 200
  client_id = create_res.json()["client_id"]
  assert client_id is not None

  # 2. Get profile
  prof_res = client.get(f"/client/profiles?client_id={client_id}")
  assert prof_res.status_code == 200
  assert prof_res.json()["client"]["name"] == "Global Corp"

  # 3. Draft reply
  draft_res = client.post("/client/draft", json={
      "client_id": client_id,
      "incoming_message": "Could you provide status on our feature deliverable?",
      "task_context": "All unit tests passing, deployed to staging.",
      "style": "professional",
  })
  assert draft_res.status_code == 200
  assert "draft" in draft_res.json()
  assert draft_res.json()["draft"]["recipient"] == "contact@global.corp"

  # 4. List threads
  threads_res = client.get("/client/threads")
  assert threads_res.status_code == 200
  assert "threads" in threads_res.json()
