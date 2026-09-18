"""Integration tests for FastAPI REST endpoints."""

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


def test_health_endpoint(api_client):
  resp = api_client.get("/health")
  assert resp.status_code == 200
  data = resp.json()
  assert data["status"] == "ok"
  assert data["app_name"] == "Xeren Assistant"


def test_tools_endpoint(api_client):
  resp = api_client.get("/tools")
  assert resp.status_code == 200
  data = resp.json()
  assert "tools" in data
  assert len(data["tools"]) >= 4


def test_query_endpoint(api_client):
  resp = api_client.post(
      "/query", json={"query": "read file README.md", "session_id": "test_s1"}
  )
  assert resp.status_code == 200
  data = resp.json()
  assert data["success"] is True
  assert "README.md" in data["response_text"]


def test_tasks_endpoint(api_client):
  # Create a task first via query
  api_client.post("/query", json={"query": "create task verify api endpoints"})
  resp = api_client.get("/tasks")
  assert resp.status_code == 200
  data = resp.json()
  assert len(data["tasks"]) >= 1
