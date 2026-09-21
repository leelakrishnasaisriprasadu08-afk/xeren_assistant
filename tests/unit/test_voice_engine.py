"""Unit tests for VoiceEngine and VoiceTool."""

from unittest.mock import MagicMock, patch
import pytest
from tools.base import Action
from tools.voice_tool import VoiceTool
from voice.engine import VoiceEngine


def test_voice_clean_text_for_speech():
  engine = VoiceEngine()
  raw_text = """### System Report
Here is the code:
```python
print("hello world")
```
Visit [our docs](https://example.com) for **critical** details. `config.json` is ready!"""

  clean = engine.clean_text(raw_text)
  assert "Code block omitted." in clean
  assert "```python" not in clean
  assert "###" not in clean
  assert "our docs" in clean
  assert "critical" in clean
  assert "`" not in clean


def test_voice_engine_list_voices():
  engine = VoiceEngine()
  voices = engine.list_voices()
  assert isinstance(voices, list)
  assert len(voices) > 0
  for v in voices:
    assert "name" in v
    assert "id" in v
    assert "gender" in v


@patch("subprocess.Popen")
def test_voice_engine_speak_async(mock_popen):
  mock_proc = MagicMock()
  mock_popen.return_value = mock_proc

  engine = VoiceEngine()
  res = engine.speak(text="Hello from Xeren Assistant", rate=1, volume=90, async_mode=True)
  assert res["status"] == "spoken"
  assert "Xeren Assistant" in res["spoken_text"]
  assert res["rate"] == 1
  assert res["volume"] == 90
  assert res["async"] is True
  mock_popen.assert_called_once()


@patch("subprocess.run")
def test_voice_engine_speak_sync(mock_run):
  mock_res = MagicMock()
  mock_res.returncode = 0
  mock_res.stderr = ""
  mock_run.return_value = mock_res

  engine = VoiceEngine()
  res = engine.speak(text="Synchronous voice message", async_mode=False)
  assert res["status"] == "spoken"
  assert res["spoken_text"] == "Synchronous voice message"
  assert res["async"] is False
  mock_run.assert_called_once()


def test_voice_engine_synthesize():
  engine = VoiceEngine()
  res = engine.synthesize(text="Autonomous speech synthesis test.")
  assert res["status"] == "synthesized"
  assert res["text"] == "Autonomous speech synthesis test."
  assert res["characters"] > 0
  assert res["estimated_duration_sec"] > 0


def test_voice_engine_transcribe():
  engine = VoiceEngine()
  res = engine.transcribe(text_or_audio="check server health and status")
  assert res["status"] == "transcribed"
  assert res["transcript"] == "check server health and status"
  assert res["confidence"] >= 0.95
  assert "server" in res["entities"]


@pytest.mark.asyncio
async def test_voice_tool_operations():
  tool = VoiceTool()

  # 1. list_voices
  act_voices = Action(action_id="v1", tool_name="voice", operation="list_voices", parameters={})
  res_voices = await tool.execute(act_voices)
  assert res_voices.success is True
  assert res_voices.data["total_voices"] > 0

  # 2. get_voice_status
  act_stat = Action(action_id="v2", tool_name="voice", operation="get_voice_status", parameters={})
  res_stat = await tool.execute(act_stat)
  assert res_stat.success is True
  assert res_stat.data["status"] == "ready"
  assert res_stat.data["tts_available"] is True

  # 3. synthesize_speech
  act_synth = Action(
      action_id="v3",
      tool_name="voice",
      operation="synthesize_speech",
      parameters={"text": "Synthesizing voice payload."},
  )
  res_synth = await tool.execute(act_synth)
  assert res_synth.success is True
  assert res_synth.data["status"] == "synthesized"

  # 4. transcribe_audio
  act_trans = Action(
      action_id="v4",
      tool_name="voice",
      operation="transcribe_audio",
      parameters={"audio_text": "build an AI portfolio website"},
  )
  res_trans = await tool.execute(act_trans)
  assert res_trans.success is True
  assert res_trans.data["transcript"] == "build an AI portfolio website"

  # 5. speak (with mock)
  with patch.object(tool.engine, "speak", return_value={"status": "spoken", "spoken_text": "Hello"}) as mock_speak:
    act_speak = Action(
        action_id="v5",
        tool_name="voice",
        operation="speak",
        parameters={"text": "Hello world", "rate": 0, "volume": 100},
    )
    res_speak = await tool.execute(act_speak)
    assert res_speak.success is True
    assert res_speak.data["status"] == "spoken"
    mock_speak.assert_called_once()

  # 6. unsupported operation
  act_invalid = Action(action_id="v6", tool_name="voice", operation="non_existent_op", parameters={})
  res_invalid = await tool.execute(act_invalid)
  assert res_invalid.success is False
  assert "Unsupported operation" in res_invalid.error
