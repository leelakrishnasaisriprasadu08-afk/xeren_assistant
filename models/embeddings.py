"""Embedding providers for vector semantic indexing and similarity retrieval."""

from abc import ABC, abstractmethod
import math
import re
from typing import Dict, List, Optional
from config.settings import Settings, get_settings


class BaseEmbeddingProvider(ABC):
  """Abstract base interface for text embedding providers."""

  @abstractmethod
  async def embed_text(self, text: str) -> List[float]:
    """Generates an embedding vector for a single text string."""
    pass

  @abstractmethod
  async def embed_batch(self, texts: List[str]) -> List[List[float]]:
    """Generates embedding vectors for a list of texts."""
    pass


class LocalTFIDFEmbeddingProvider(BaseEmbeddingProvider):
  """Deterministic, zero-dependency character/token n-gram embedding provider.

  Produces normalized vector representations for offline environments and
  tests.
  """

  def __init__(self, vector_dim: int = 128):
    self.vector_dim = vector_dim

  def _compute_vector(self, text: str) -> List[float]:
    clean = re.sub(r"[^\w\s]", " ", text.lower())
    tokens = clean.split()
    if not tokens:
      return [0.0] * self.vector_dim

    vec = [0.0] * self.vector_dim
    for token in tokens:
      # Deterministic hash bucket
      h = 0
      for ch in token:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
      bucket = h % self.vector_dim
      vec[bucket] += 1.0

    # L2 normalize vector
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
      vec = [x / norm for x in vec]
    return vec

  async def embed_text(self, text: str) -> List[float]:
    return self._compute_vector(text)

  async def embed_batch(self, texts: List[str]) -> List[List[float]]:
    return [self._compute_vector(t) for t in texts]


class GeminiEmbeddingProvider(BaseEmbeddingProvider):
  """Google GenAI Embedding Provider using text-embedding-004."""

  def __init__(
      self,
      api_key: Optional[str] = None,
      model_name: str = "gemini-embedding-001",
      fallback_provider: Optional[BaseEmbeddingProvider] = None,
  ):
    settings = get_settings()
    self.api_key = api_key or getattr(settings, "gemini_api_key", None)
    self.model_name = model_name
    self.fallback = fallback_provider or LocalTFIDFEmbeddingProvider()
    self._client = None
    if self.api_key:
      try:
        from google import genai

        self._client = genai.Client(api_key=self.api_key)
      except Exception:
        pass

  async def embed_text(self, text: str) -> List[float]:
    if self._client:
      try:
        res = self._client.models.embed_content(
            model=self.model_name,
            contents=text,
        )
        if res.embedding and res.embedding.values:
          return list(res.embedding.values)
      except Exception:
        pass
    return await self.fallback.embed_text(text)

  async def embed_batch(self, texts: List[str]) -> List[List[float]]:
    results = []
    for t in texts:
      results.append(await self.embed_text(t))
    return results


def get_default_embedding_provider(
    settings: Optional[Settings] = None,
) -> BaseEmbeddingProvider:
  """Factory returning default configured embedding provider."""
  current_settings = settings or get_settings()
  api_key = getattr(current_settings, "gemini_api_key", None)
  if api_key:
    return GeminiEmbeddingProvider(api_key=api_key)
  return LocalTFIDFEmbeddingProvider()
