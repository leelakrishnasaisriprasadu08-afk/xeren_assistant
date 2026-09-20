"""Integration tests for Phase 8: Universal Device Automation & Task Scheduling."""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.api import create_app
from core.assistant import XerenAssistant
from core.intent import IntentClassifier, IntentType
from core.planner import TaskPlanner
from core.scheduler import TaskScheduler
from models.provider import MockLLMProvider


from config.settings import Settings


@pytest.fixture
def mock_assistant(tmp_path: Path) -> XerenAssistant:
  settings = Settings(
      workspace_root=tmp_path / "sandbox",
      db_path=tmp_path / "data" / "xeren_test.sqlite",
      traces_dir=tmp_path / "traces",
      preferences_path=tmp_path / "config" / "preferences.yaml",
  )
  settings.workspace_root.mkdir(parents=True, exist_ok=True)
  llm = MockLLMProvider()
  return XerenAssistant(
      settings=settings,
      llm_provider=llm,
  )


@pytest.mark.asyncio
async def test_device_intent_classification():
  classifier = IntentClassifier()

  intent_stats = await classifier.classify("what is my current cpu and ram usage?")
  assert intent_stats.intent_type == IntentType.DEVICE

  intent_screen = await classifier.classify("take a screenshot of desktop")
  assert intent_screen.intent_type == IntentType.DEVICE

  intent_app = await classifier.classify("launch notepad")
  assert intent_app.intent_type == IntentType.DEVICE

  intent_sched = await classifier.classify("schedule a health check every 5 minutes")
  assert intent_sched.intent_type == IntentType.SCHEDULE


@pytest.mark.asyncio
async def test_device_planner_dag():
  planner = TaskPlanner()
  classifier = IntentClassifier()

  # Test system stats DAG
  intent_stats = await classifier.classify("system stats")
  dag_stats = await planner.plan_dag("system stats", intent_stats)
  assert len(dag_stats.actions) == 1
  assert dag_stats.actions[0].tool_name == "device"
  assert dag_stats.actions[0].operation == "get_system_info"

  # Test screenshot DAG
  intent_screen = await classifier.classify("take screenshot")
  dag_screen = await planner.plan_dag("take screenshot", intent_screen)
  assert len(dag_screen.actions) == 1
  assert dag_screen.actions[0].tool_name == "device"
  assert dag_screen.actions[0].operation == "capture_screenshot"

  # Test process list DAG
  intent_proc = await classifier.classify("list processes")
  dag_proc = await planner.plan_dag("list processes", intent_proc)
  assert len(dag_proc.actions) == 1
  assert dag_proc.actions[0].tool_name == "device"
  assert dag_proc.actions[0].operation == "list_processes"


@pytest.mark.asyncio
async def test_assistant_device_execution(mock_assistant: XerenAssistant):
  # Execute system stats query
  resp = await mock_assistant.process_request("what is my system stats?")
  assert resp.success is True
  assert "System Telemetry" in resp.response_text or "CPU" in resp.response_text

  # Execute list processes query
  resp_proc = await mock_assistant.process_request("list processes")
  assert resp_proc.success is True
  assert "Active Running Processes" in resp_proc.response_text


def test_api_device_and_scheduler_endpoints(mock_assistant: XerenAssistant):
  app = create_app(assistant=mock_assistant)
  client = TestClient(app)

  # 1. Device stats endpoint
  res_stats = client.get("/device/stats")
  assert res_stats.status_code == 200
  data = res_stats.json()
  assert "platform" in data
  assert "cpu" in data

  # 1b. Server health check endpoint
  res_srv = client.get("/system/server-check")
  assert res_srv.status_code == 200
  srv_data = res_srv.json()
  assert "health_score" in srv_data
  assert "overall_status" in srv_data

  # 1c. Network ports endpoint
  res_net = client.get("/device/network-ports")
  assert res_net.status_code == 200
  net_data = res_net.json()
  assert "hostname" in net_data

  # 2. Device processes endpoint
  res_procs = client.get("/device/processes?limit=5")
  assert res_procs.status_code == 200
  assert "processes" in res_procs.json()

  # 3. Scheduler endpoints
  res_create_job = client.post(
      "/scheduler/jobs",
      json={
          "name": "Integration Test Health Check",
          "interval_seconds": 300.0,
          "action_type": "query",
          "payload": {"query": "system stats"},
      },
  )
  assert res_create_job.status_code == 200
  job_data = res_create_job.json()
  job_id = job_data["job_id"]
  assert job_data["name"] == "Integration Test Health Check"

  # List jobs
  res_list = client.get("/scheduler/jobs")
  assert res_list.status_code == 200
  jobs = res_list.json()["jobs"]
  assert any(j["job_id"] == job_id for j in jobs)

  # Cancel job
  res_cancel = client.delete(f"/scheduler/jobs/{job_id}")
  assert res_cancel.status_code == 200
  assert res_cancel.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_assistant_server_check_flow(mock_assistant: XerenAssistant):
  resp = await mock_assistant.process_request("run a server check on this system")
  assert resp.success is True
  assert "Health Audit" in resp.response_text or "Score" in resp.response_text

