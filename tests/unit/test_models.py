"""Unit tests for the LLM Provider interface and mock provider."""

import pytest
from models.base import LLMMessage
from models.provider import MockLLMProvider, get_default_llm_provider


@pytest.mark.asyncio
async def test_mock_llm_provider_generation():
  provider = MockLLMProvider(canned_response="Hello from mock provider!")
  messages = [LLMMessage(role="user", content="Hi Xeren")]

  response = await provider.generate(messages)
  assert response.text == "Hello from mock provider!"
  assert response.usage.total_tokens > 0
  assert len(provider.call_history) == 1


def test_get_default_provider_fallback(test_settings):
  # In test environment, if no valid real key, it cleanly falls back to mock provider
  provider = get_default_llm_provider(test_settings)
  assert provider is not None
