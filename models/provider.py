"""Concrete LLM Provider implementations for Phase 1."""

import os
from typing import Any, Dict, List, Optional
from config.settings import Settings, get_settings
from security.secrets import SecretStore
from .base import BaseLLMProvider, LLMMessage, LLMResponse, LLMUsage


class GeminiProvider(BaseLLMProvider):
  """Google Gemini LLM provider implementation for Phase 1."""

  def __init__(
      self,
      api_key: Optional[str] = None,
      model_name: str = "gemini-3.5-flash",
  ):
    self.model_name = model_name
    settings = get_settings()
    self.api_key = (
        api_key
        or getattr(settings, "gemini_api_key", None)
        or SecretStore.get_instance().get_secret("GEMINI_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
    )

    if not self.api_key:
      raise ValueError(
          "GEMINI_API_KEY is required to initialize GeminiProvider."
      )

    # Lazy-load genai client
    from google import genai

    self.client = genai.Client(api_key=self.api_key)

  async def generate(
      self,
      messages: List[LLMMessage],
      system_instruction: Optional[str] = None,
      temperature: float = 0.2,
      response_schema: Optional[Any] = None,
  ) -> LLMResponse:
    # Format contents
    contents = []
    for msg in messages:
      role = "user" if msg.role in ["user", "system"] else "model"
      contents.append({"role": role, "parts": [{"text": msg.content}]})

    config_kwargs: Dict[str, Any] = {
        "temperature": temperature,
    }
    if system_instruction:
      config_kwargs["system_instruction"] = system_instruction
    if response_schema:
      config_kwargs["response_mime_type"] = "application/json"
      config_kwargs["response_schema"] = response_schema

    models_to_try = [self.model_name, "gemini-3.5-flash", "gemini-3.5-flash-lite"]
    last_err = None

    for m in models_to_try:
      try:
        response = self.client.models.generate_content(
            model=m,
            contents=contents,
            config=config_kwargs,
        )
        text = response.text or ""
        return LLMResponse(
            text=text,
            raw_response=response,
            model_name=m,
            usage=LLMUsage(
                prompt_tokens=getattr(
                    response.usage_metadata, "prompt_token_count", 0
                ),
                completion_tokens=getattr(
                    response.usage_metadata, "candidates_token_count", 0
                ),
                total_tokens=getattr(
                    response.usage_metadata, "total_token_count", 0
                ),
            ),
        )
      except Exception as e:
        last_err = e
        continue

    raise RuntimeError(f"Gemini API generation error: {str(last_err)}")

  async def generate_vision(
      self,
      prompt: str,
      image_bytes: bytes,
      mime_type: str = "image/png",
      system_instruction: Optional[str] = None,
  ) -> LLMResponse:
    from google.genai import types

    contents = [
        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        prompt,
    ]
    config_kwargs: Dict[str, Any] = {"temperature": 0.2}
    if system_instruction:
      config_kwargs["system_instruction"] = system_instruction

    try:
      response = self.client.models.generate_content(
          model=self.model_name,
          contents=contents,
          config=config_kwargs,
      )
      text = response.text or ""
      return LLMResponse(
          text=text,
          raw_response=response,
          model_name=self.model_name,
      )
    except Exception as e:
      raise RuntimeError(f"Gemini Vision API generation error: {str(e)}")


class MockLLMProvider(BaseLLMProvider):
  """Deterministic Mock LLM Provider for offline development and testing."""

  def __init__(self, canned_response: Optional[str] = None):
    self.canned_response = canned_response or "Mock LLM completion response."
    self.call_history: List[List[LLMMessage]] = []

  async def generate(
      self,
      messages: List[LLMMessage],
      system_instruction: Optional[str] = None,
      temperature: float = 0.2,
      response_schema: Optional[Any] = None,
  ) -> LLMResponse:
    self.call_history.append(messages)
    return LLMResponse(
        text=self.canned_response,
        model_name="mock-llm-v1",
        usage=LLMUsage(
            prompt_tokens=10, completion_tokens=15, total_tokens=25
        ),
    )

  async def generate_vision(
      self,
      prompt: str,
      image_bytes: bytes,
      mime_type: str = "image/png",
      system_instruction: Optional[str] = None,
  ) -> LLMResponse:
    return LLMResponse(
        text="### Screen Vision Analysis\n- **Visible Application**: Visual Studio Code & Terminal\n- **Active Elements**: Editor canvas, file tree, system taskbar\n- **Diagnostics**: No active error dialogs detected.",
        model_name="mock-vision",
    )


def get_default_llm_provider(
    settings: Optional[Settings] = None,
) -> BaseLLMProvider:
  """Factory initializing the configured LLM provider."""
  current_settings = settings or get_settings()
  api_key = (
      current_settings.gemini_api_key
      or SecretStore.get_instance().get_secret("GEMINI_API_KEY")
      or os.environ.get("GEMINI_API_KEY")
  )

  if api_key and api_key != "your_gemini_api_key_here":
    try:
      return GeminiProvider(api_key=api_key)
    except Exception:
      pass

  # Fallback to Mock Provider if no active API key provided
  return MockLLMProvider()
