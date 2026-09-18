"""Unit tests for embedding providers and SemanticMemoryStore."""

import pytest
from memory.semantic import SemanticMemoryStore, cosine_similarity
from models.embeddings import LocalTFIDFEmbeddingProvider


@pytest.mark.asyncio
async def test_local_tfidf_embeddings():
  """Test that LocalTFIDFEmbeddingProvider creates normalized non-empty vectors."""
  provider = LocalTFIDFEmbeddingProvider(vector_dim=64)
  vec1 = await provider.embed_text("python async fastapi")
  vec2 = await provider.embed_text("python async asyncio")
  vec3 = await provider.embed_text("gardening plants soil")

  assert len(vec1) == 64
  assert len(vec2) == 64

  sim_similar = cosine_similarity(vec1, vec2)
  sim_different = cosine_similarity(vec1, vec3)

  assert sim_similar > sim_different
  assert sim_similar > 0.0


@pytest.mark.asyncio
async def test_semantic_memory_crud_and_search(tmp_path):
  """Test storing and searching memory records in SemanticMemoryStore."""
  db_file = tmp_path / "test_mem.sqlite"
  provider = LocalTFIDFEmbeddingProvider(vector_dim=64)
  store = SemanticMemoryStore(db_path=db_file, embedding_provider=provider)

  # 1. Add memories
  m1 = await store.add_memory(
      content="SQLite database locks on Windows if connection is left unclosed",
      category="debugging",
      metadata={"issue": "db_lock"},
  )
  m2 = await store.add_memory(
      content="DuckDuckGo rate limits can be mitigated with retry backoff",
      category="networking",
      metadata={"issue": "rate_limit"},
  )
  m3 = await store.add_memory(
      content="Kahn topological sort partitions DAG actions into parallel waves",
      category="algorithm",
      metadata={"topic": "dag"},
  )

  assert m1.memory_id is not None

  # 2. Search query related to SQLite Windows
  results = await store.search(query="Windows SQLite connection lock", limit=2)
  assert len(results) > 0
  assert "SQLite database locks" in results[0].memory.content
  assert results[0].similarity_score > 0.3

  # 3. Category filtering
  dag_results = await store.search(
      query="topological sort", category="algorithm"
  )
  assert len(dag_results) == 1
  assert "Kahn" in dag_results[0].memory.content

  # 4. List memories
  all_mems = store.list_memories()
  assert len(all_mems) == 3
