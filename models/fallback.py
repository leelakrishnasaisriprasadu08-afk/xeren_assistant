"""Multi-Provider LLM Fallback Engine for automatic failover."""

from typing import Any, List, Optional
from .base import BaseLLMProvider, LLMMessage, LLMResponse


class FallbackLLMProvider(BaseLLMProvider):
  """Orchestrates multiple LLM providers with automatic fallback on rate limits or failures."""

  def __init__(
      self,
      primary: BaseLLMProvider,
      fallbacks: Optional[List[BaseLLMProvider]] = None,
  ):
    self.primary = primary
    self.fallbacks = fallbacks or []
    self.last_used_provider: Optional[BaseLLMProvider] = None
    self.fallback_history: List[dict] = []

  @property
  def all_providers(self) -> List[BaseLLMProvider]:
    return [self.primary] + self.fallbacks

  async def generate(
      self,
      messages: List[LLMMessage],
      system_instruction: Optional[str] = None,
      temperature: float = 0.2,
      response_schema: Optional[Any] = None,
  ) -> LLMResponse:
    errors = []

    for idx, provider in enumerate(self.all_providers):
      try:
        response = await provider.generate(
            messages=messages,
            system_instruction=system_instruction,
            temperature=temperature,
            response_schema=response_schema,
        )
        self.last_used_provider = provider
        if idx > 0:
          self.fallback_history.append({
              "fallback_index": idx,
              "provider_model": response.model_name,
              "recovered": True,
          })
        return response
      except Exception as e:
        errors.append(f"Provider {idx} ({type(provider).__name__}) failed: {str(e)}")

    raise RuntimeError(
        "All LLM providers in fallback chain failed:\n" + "\n".join(errors)
    )
