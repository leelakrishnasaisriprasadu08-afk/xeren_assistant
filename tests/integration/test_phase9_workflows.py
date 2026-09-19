"""Integration tests for Phase 9: Multi-Modal Screen Vision & Autonomous Browser Workflows."""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.api import create_app
from config.settings import Settings
from core.assistant import XerenAssistant
from core.intent import IntentClassifier, IntentType
from core.planner import TaskPlanner
from models.provider import MockLLMProvider


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
  return XerenAssistant(settings=settings, llm_provider=llm)


@pytest.mark.asyncio
async def test_phase9_intent_classification():
  classifier = IntentClassifier()

  intent_vis = await classifier.classify("look at my screen and tell me what is open")
  assert intent_vis.intent_type == IntentType.VISION

  intent_vis_text = await classifier.classify("read screen text and diagnose error")
  assert intent_vis_text.intent_type == IntentType.VISION

  intent_browse = await classifier.classify("navigate to https://news.ycombinator.com and summarize")
  assert intent_browse.intent_type == IntentType.BROWSER
  assert intent_browse.entities.get("url") == "https://news.ycombinator.com"


@pytest.mark.asyncio
async def test_phase9_planner_dag():
  planner = TaskPlanner()
  classifier = IntentClassifier()

  # Vision Plan
  intent_vis = await classifier.classify("analyze my screen")
  dag_vis = await planner.plan_dag("analyze my screen", intent_vis)
  assert len(dag_vis.actions) == 1
  assert dag_vis.actions[0].tool_name == "vision"
  assert dag_vis.actions[0].operation == "analyze_screen"

  # Browser Plan
  intent_browse = await classifier.classify("extract article from https://example.com")
  dag_browse = await planner.plan_dag("extract article from https://example.com", intent_browse)
  assert len(dag_browse.actions) == 1
  assert dag_browse.actions[0].tool_name == "browser"
  assert dag_browse.actions[0].operation == "extract_page_content"


@pytest.mark.asyncio
async def test_phase9_assistant_vision_query(mock_assistant: XerenAssistant):
  resp = await mock_assistant.process_request("look at my screen and explain what is open")
  assert resp.success is True
  assert "Screen Vision Analysis" in resp.response_text or "Vision" in resp.response_text


def test_phase9_api_endpoints(mock_assistant: XerenAssistant):
  app = create_app(assistant=mock_assistant)
  client = TestClient(app)

  # 1. Vision Endpoint
  res_vis = client.post("/vision/analyze-screen", json={"prompt": "Inspect active desktop"})
  assert res_vis.status_code == 200
  data = res_vis.json()
  assert "analysis" in data

  # 2. Vision Text Endpoint
  res_txt = client.post("/vision/extract-text")
  assert res_txt.status_code == 200
  assert "analysis" in res_txt.json()
