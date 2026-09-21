"""Integration tests for Chat History, Episodic Summaries, and Session Management API."""

import pytest
from app.api import create_app
from core.assistant import XerenAssistant
from fastapi.testclient import TestClient
from models.provider import MockLLMProvider
from tools.registry import get_default_registry


@pytest.fixture
def api_client(test_settings):
  registry = get_default_registry(test_settings)
  mock_llm = MockLLMProvider()
  assistant = XerenAssistant(
      settings=test_settings, tool_registry=registry, llm_provider=mock_llm
  )
  app = create_app(assistant)
  return TestClient(app)


def test_chat_history_lifecycle(api_client):
  # 1. Execute two queries in a dedicated session
  sess_id = "session_research_alpha"
  res1 = api_client.post(
      "/query",
      json={
          "query": "search online for python fastapi benchmarks",
          "session_id": sess_id,
      },
  )
  assert res1.status_code == 200

  res2 = api_client.post(
      "/query",
      json={
          "query": "build website portfolio with sleek dark mode",
          "session_id": sess_id,
      },
  )
  assert res2.status_code == 200

  # 2. List sessions
  list_res = api_client.get("/history/sessions")
  assert list_res.status_code == 200
  sessions = list_res.json().get("sessions", [])
  assert len(sessions) >= 1

  # Find our session
  target = next((s for s in sessions if s["session_id"] == sess_id), None)
  assert target is not None
  assert len(target["title"]) > 5
  assert target["message_count"] >= 4  # 2 user queries + 2 assistant responses

  # 3. Get session details
  details_res = api_client.get(f"/history/sessions/{sess_id}")
  assert details_res.status_code == 200
  details = details_res.json()
  assert details["session"]["session_id"] == sess_id
  assert len(details["messages"]) >= 4

  # 4. Rename session title
  new_title = "Deep Architectural Analysis and Full-Stack Portfolio Deployment"
  rename_res = api_client.post(
      f"/history/sessions/{sess_id}/title",
      json={"title": new_title},
  )
  assert rename_res.status_code == 200
  assert rename_res.json()["title"] == new_title

  # Verify title updated
  details_res2 = api_client.get(f"/history/sessions/{sess_id}")
  assert details_res2.json()["session"]["title"] == new_title

  # 5. Delete specific session
  del_res = api_client.delete(f"/history/sessions/{sess_id}")
  assert del_res.status_code == 200

  # Verify deletion
  details_res3 = api_client.get(f"/history/sessions/{sess_id}")
  assert details_res3.status_code == 404

  # 6. Clear all history
  clear_res = api_client.post("/history/clear")
  assert clear_res.status_code == 200
  list_after_clear = api_client.get("/history/sessions").json().get("sessions", [])
  assert len(list_after_clear) == 0
