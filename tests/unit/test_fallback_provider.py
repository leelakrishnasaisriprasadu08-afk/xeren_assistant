"""Unit tests for Multi-Provider Fallback engine."""

import pytest
from models.base import LLMMessage
from models.fallback import FallbackLLMProvider
from models.provider import MockLLMProvider


class FailingLLMProvider(MockLLMProvider):

  async def generate(self, *args, **kwargs):
    raise ConnectionError("Primary provider rate limited (HTTP 429)")


@pytest.mark.asyncio
async def test_fallback_provider_switches_on_failure():
  primary = FailingLLMProvider()
  secondary = MockLLMProvider(canned_response="Secondary fallback response")

  fallback_engine = FallbackLLMProvider(primary=primary, fallbacks=[secondary])
  messages = [LLMMessage(role="user", content="Hello")]

  resp = await fallback_engine.generate(messages)

  assert resp.text == "Secondary fallback response"
  assert len(fallback_engine.fallback_history) == 1
  assert fallback_engine.fallback_history[0]["recovered"] is True


@pytest.mark.asyncio
async def test_fallback_provider_fails_if_all_fail():
  p1 = FailingLLMProvider()
  p2 = FailingLLMProvider()

  fallback_engine = FallbackLLMProvider(primary=p1, fallbacks=[p2])
  messages = [LLMMessage(role="user", content="Hello")]

  with pytest.raises(RuntimeError, match="All LLM providers in fallback chain failed"):
    await fallback_engine.generate(messages)
