"""Integration tests for Phase 5 workflows: Background Scheduler, Swarm API, and Flamegraph endpoints."""

import pytest
from app.api import create_app
from config.settings import Settings
from core.assistant import XerenAssistant
from fastapi.testclient import TestClient
from models.base import BaseLLMProvider, LLMResponse


class MockPhase5LLM(BaseLLMProvider):
  async def generate(self, messages, system_instruction=None, temperature=0.0):
    user_prompt = messages[0].content
    if "Research Goal" in user_prompt:
      return LLMResponse(
          text="### Research Dossier\n- Modern FastAPI architectures use background asyncio tasks.",
          model_name="mock-researcher",
      )
    elif "Audit code" in user_prompt:
      return LLMResponse(
          text="### Security Audit\n- Status: PASSED",
          model_name="mock-reviewer",
      )
    else:
      return LLMResponse(
          text="```python\n# Enterprise Phase 5 Implementation\ndef main():\n    pass\n```",
          model_name="mock-llm",
      )


@pytest.fixture
def phase5_client(tmp_path):
  """Creates a test client for FastAPI with Phase 5 endpoints."""
  settings = Settings(
      workspace_root=tmp_path / "sandbox",
      db_path=tmp_path / "data" / "xeren_p5.sqlite",
      traces_dir=tmp_path / "traces",
      preferences_path=tmp_path / "config" / "preferences.yaml",
  )
  settings.workspace_root.mkdir(parents=True, exist_ok=True)
  llm = MockPhase5LLM()

  assistant = XerenAssistant(settings=settings, llm_provider=llm)
  app = create_app(assistant=assistant)
  return TestClient(app)


def test_api_scheduler_job_lifecycle(phase5_client):
  """Test creating, listing, and deleting a scheduled background job via REST API."""
  # 1. Create job
  post_res = phase5_client.post(
      "/jobs",
      json={
          "name": "Periodic Health Scan",
          "interval_seconds": 60,
          "action_type": "health_scan",
      },
  )
  assert post_res.status_code == 200
  job_data = post_res.json()["job"]
  job_id = job_data["job_id"]
  assert job_data["name"] == "Periodic Health Scan"

  # 2. List jobs
  get_res = phase5_client.get("/jobs")
  assert get_res.status_code == 200
  jobs_list = get_res.json()["jobs"]
  assert len(jobs_list) >= 1
  assert any(j["job_id"] == job_id for j in jobs_list)

  # 3. Delete job
  del_res = phase5_client.delete(f"/jobs/{job_id}")
  assert del_res.status_code == 200
  assert del_res.json()["status"] == "deleted"


def test_api_swarm_collaboration_endpoint(phase5_client):
  """Test triggering autonomous multi-agent swarm collaboration via REST API."""
  res = phase5_client.post(
      "/swarm/run",
      json={"prompt": "Design a resilient microservices rate limiter in Python"},
  )
  assert res.status_code == 200
  data = res.json()

  assert data["consensus_reached"] is True
  assert len(data["turns"]) >= 3
  assert "def main():" in data["final_artifact"]


def test_api_trace_flamegraph_endpoint(phase5_client):
  """Test executing a query and retrieving its flamegraph timing breakdown."""
  # 1. Query assistant
  q_res = phase5_client.post(
      "/query", json={"query": "Hello Xeren Phase 5"}
  )
  assert q_res.status_code == 200
  trace_id = q_res.json()["trace_id"]
  assert trace_id

  # 2. Query flamegraph
  fg_res = phase5_client.get(f"/traces/{trace_id}/flamegraph")
  assert fg_res.status_code == 200
  fg_data = fg_res.json()

  assert fg_data["name"].startswith("Request:")
  assert len(fg_data["children"]) >= 2
