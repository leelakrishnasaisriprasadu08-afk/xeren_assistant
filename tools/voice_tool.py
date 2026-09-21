"""Voice Assistant Tool for Xeren Assistant.

Enables autonomous speech synthesis, voice response output, audio transcription,
and system voice discovery.
"""

import time
from typing import Any, Dict, List, Optional
from voice.engine import VoiceEngine
from .base import Action, BaseTool, ToolResult


class VoiceTool(BaseTool):
  """Tool for voice interaction, speech output, and transcription."""

  def __init__(self, engine: Optional[VoiceEngine] = None):
    self.engine = engine or VoiceEngine()

  @property
  def name(self) -> str:
    return "voice"

  @property
  def description(self) -> str:
    return (
        "Voice Assistant Tool: speaks text out loud with native speech synthesis,"
        " synthesizes voice responses, transcribes user voice input, and lists"
        " available voices."
    )

  @property
  def supported_operations(self) -> List[str]:
    return [
        "speak",
        "synthesize_speech",
        "transcribe_audio",
        "list_voices",
        "get_voice_status",
    ]

  async def execute(self, action: Action) -> ToolResult:
    start_time = time.perf_counter()
    op = action.operation.lower()
    params = action.parameters or {}

    try:
      if op == "speak":
        text = params.get("text") or params.get("message") or "Hello! I am Xeren, your autonomous AI assistant."
        voice = params.get("voice")
        rate = int(params["rate"]) if params.get("rate") is not None else None
        volume = int(params["volume"]) if params.get("volume") is not None else None
        async_mode = params.get("async_mode", True)
        data = self.engine.speak(text=text, voice=voice, rate=rate, volume=volume, async_mode=async_mode)

      elif op == "synthesize_speech":
        text = params.get("text") or "Speech synthesis test."
        data = self.engine.synthesize(text=text)

      elif op == "transcribe_audio":
        audio_text = params.get("audio_text") or params.get("transcript") or params.get("text") or ""
        data = self.engine.transcribe(text_or_audio=audio_text)

      elif op == "list_voices":
        voices = self.engine.list_voices()
        data = {"voices": voices, "total_voices": len(voices)}

      elif op == "get_voice_status":
        voices = self.engine.list_voices()
        data = {
            "status": "ready",
            "tts_available": True,
            "stt_available": True,
            "total_voices": len(voices),
            "engine": "Windows SAPI + Web Speech Synthesis API",
        }

      else:
        raise ValueError(f"Unsupported operation '{op}' on tool '{self.name}'")

      elapsed = (time.perf_counter() - start_time) * 1000
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=True,
          data=data,
          execution_time_ms=elapsed,
      )

    except Exception as e:
      elapsed = (time.perf_counter() - start_time) * 1000
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=False,
          error=str(e),
          execution_time_ms=elapsed,
      )
