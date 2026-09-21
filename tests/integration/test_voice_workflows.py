"""Integration tests for Voice Assistant workflows, intent classification, DAG execution, and REST endpoints."""

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import pytest
from app.api import create_app
from core.assistant import XerenAssistant
from core.intent import IntentClassifier, IntentType
from core.planner import TaskPlanner
from voice.engine import VoiceEngine


@pytest.mark.asyncio
async def test_voice_intent_classification():
  classifier = IntentClassifier()

  res1 = await classifier.classify("speak hello world out loud")
  assert res1.intent_type == IntentType.VOICE

  res2 = await classifier.classify("say all systems are operational")
  assert res2.intent_type == IntentType.VOICE

  res3 = await classifier.classify("read aloud the latest notification")
  assert res3.intent_type == IntentType.VOICE

  res4 = await classifier.classify("synthesize speech for server audit")
  assert res4.intent_type == IntentType.VOICE

  res5 = await classifier.classify("list available system voices")
  assert res5.intent_type == IntentType.VOICE


@pytest.mark.asyncio
async def test_voice_dag_planner():
  planner = TaskPlanner()
  classifier = IntentClassifier()

  intent_res = await classifier.classify("speak all systems operational out loud")
  plan = await planner.plan("speak all systems operational out loud", intent_res)

  assert len(plan) == 1
  assert plan[0].tool_name == "voice"
  assert plan[0].operation == "speak"
  assert "all systems operational" in plan[0].parameters.get("text", "")


@pytest.mark.asyncio
async def test_voice_assistant_end_to_end(test_settings):
  assistant = XerenAssistant(settings=test_settings)

  # Mock out actual audio playback so test runs headlessly and quickly
  with patch.object(
      assistant.tool_registry.get_tool("voice").engine,
      "speak",
      return_value={"status": "spoken", "spoken_text": "all systems operational", "async": True},
  ):
    resp = await assistant.process_request("speak all systems operational out loud")
    assert resp.success is True
    assert "voice" in resp.tools_used
    assert "Voice Speech Synthesized" in resp.response_text


def test_voice_rest_api_endpoints(test_settings):
  assistant = XerenAssistant(settings=test_settings)
  app = create_app(assistant=assistant)
  client = TestClient(app)

  # 1. GET /voice/status
  res_stat = client.get("/voice/status")
  assert res_stat.status_code == 200
  data_stat = res_stat.json()
  assert data_stat["status"] == "ready"
  assert data_stat["tts_available"] is True

  # 2. GET /voice/voices
  res_voices = client.get("/voice/voices")
  assert res_voices.status_code == 200
  data_voices = res_voices.json()
  assert "voices" in data_voices
  assert len(data_voices["voices"]) > 0

  # 3. POST /voice/synthesize
  res_synth = client.post("/voice/synthesize", json={"text": "Integration test speech synthesis."})
  assert res_synth.status_code == 200
  data_synth = res_synth.json()
  assert data_synth["status"] == "synthesized"
  assert data_synth["characters"] > 0

  # 4. POST /voice/transcribe
  res_trans = client.post("/voice/transcribe", json={"audio_text": "check server health and security status"})
  assert res_trans.status_code == 200
  data_trans = res_trans.json()
  assert data_trans["transcript"] == "check server health and security status"
  assert "server" in data_trans["entities"]

  # 5. POST /voice/speak (mocked)
  with patch.object(
      assistant.tool_registry.get_tool("voice").engine,
      "speak",
      return_value={"status": "spoken", "spoken_text": "API Speak Test", "async": True},
  ):
    res_speak = client.post(
        "/voice/speak",
        json={"text": "API Speak Test", "rate": 0, "volume": 100, "async_mode": True},
    )
    assert res_speak.status_code == 200
    data_speak = res_speak.json()
    assert data_speak["status"] == "spoken"
