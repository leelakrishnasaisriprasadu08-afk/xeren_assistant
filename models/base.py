"""Abstract Base LLM Provider models and interfaces."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
  """A single message exchanged in conversation history."""

  role: str = Field(description="Role: 'user', 'assistant', or 'system'")
  content: str = Field(description="Text message content")


class LLMUsage(BaseModel):
  """Token usage metrics."""

  prompt_tokens: int = 0
  completion_tokens: int = 0
  total_tokens: int = 0


class LLMResponse(BaseModel):
  """Standardized LLM generation response."""

  text: str
  raw_response: Any = None
  usage: LLMUsage = Field(default_factory=LLMUsage)
  model_name: str = ""


class BaseLLMProvider(ABC):
  """Abstract interface for all LLM providers in Xeren Assistant."""

  @abstractmethod
  async def generate(
      self,
      messages: List[LLMMessage],
      system_instruction: Optional[str] = None,
      temperature: float = 0.2,
      response_schema: Optional[Any] = None,
  ) -> LLMResponse:
    """Generates a completion from the LLM given conversation messages."""
    pass
