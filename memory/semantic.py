"""Long-term semantic and episodic memory storage backed by SQLite and vector embeddings."""

from contextlib import closing
import json
import math
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field
from models.embeddings import BaseEmbeddingProvider, get_default_embedding_provider


class MemoryRecord(BaseModel):
  """Individual record stored in semantic memory."""

  memory_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
  content: str
  category: str = "general"
  metadata: Dict[str, Any] = Field(default_factory=dict)
  embedding: List[float] = Field(default_factory=list)
  created_at: float = Field(default_factory=time.time)


class MemorySearchResult(BaseModel):
  """Result of a semantic similarity query."""

  memory: MemoryRecord
  similarity_score: float
  match_type: str = "hybrid"


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
  """Computes cosine similarity between two numeric vectors."""
  if not v1 or not v2 or len(v1) != len(v2):
    return 0.0
  dot = sum(a * b for a, b in zip(v1, v2))
  norm1 = math.sqrt(sum(a * a for a in v1))
  norm2 = math.sqrt(sum(b * b for b in v2))
  if norm1 == 0.0 or norm2 == 0.0:
    return 0.0
  return dot / (norm1 * norm2)


class SemanticMemoryStore:
  """Long-term semantic memory storage with hybrid vector & keyword retrieval."""

  def __init__(
      self,
      db_path: Optional[Path] = None,
      embedding_provider: Optional[BaseEmbeddingProvider] = None,
  ):
    self.db_path = (db_path or Path("data/xeren.sqlite")).resolve()
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
    self.embedding_provider = (
        embedding_provider or get_default_embedding_provider()
    )
    self._init_db()

  def _get_connection(self) -> sqlite3.Connection:
    conn = sqlite3.connect(str(self.db_path))
    conn.row_factory = sqlite3.Row
    return conn

  def _init_db(self) -> None:
    with closing(self._get_connection()) as conn:
      with conn:
        conn.execute("""
              CREATE TABLE IF NOT EXISTS semantic_memory (
                  memory_id TEXT PRIMARY KEY,
                  content TEXT NOT NULL,
                  category TEXT NOT NULL,
                  metadata_json TEXT NOT NULL,
                  embedding_json TEXT NOT NULL,
                  created_at REAL NOT NULL
              )
              """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mem_category ON"
            " semantic_memory(category)"
        )

  async def add_memory(
      self,
      content: str,
      category: str = "general",
      metadata: Optional[Dict[str, Any]] = None,
  ) -> MemoryRecord:
    """Embeds and persists a new memory item."""
    embedding = await self.embedding_provider.embed_text(content)
    record = MemoryRecord(
        content=content,
        category=category,
        metadata=metadata or {},
        embedding=embedding,
    )

    with closing(self._get_connection()) as conn:
      with conn:
        conn.execute(
            """
                  INSERT INTO semantic_memory (memory_id, content, category, metadata_json, embedding_json, created_at)
                  VALUES (?, ?, ?, ?, ?, ?)
                  """,
            (
                record.memory_id,
                record.content,
                record.category,
                json.dumps(record.metadata),
                json.dumps(record.embedding),
                record.created_at,
            ),
        )

    return record

  async def search(
      self,
      query: str,
      limit: int = 5,
      min_score: float = 0.1,
      category: Optional[str] = None,
  ) -> List[MemorySearchResult]:
    """Searches memory items using cosine similarity over query embedding."""
    query_vector = await self.embedding_provider.embed_text(query)
    query_words = set(query.lower().split())

    with closing(self._get_connection()) as conn:
      if category:
        cursor = conn.execute(
            "SELECT memory_id, content, category, metadata_json, embedding_json,"
            " created_at FROM semantic_memory WHERE category = ?",
            (category,),
        )
      else:
        cursor = conn.execute(
            "SELECT memory_id, content, category, metadata_json, embedding_json,"
            " created_at FROM semantic_memory"
        )
      rows = cursor.fetchall()

    results: List[MemorySearchResult] = []
    for row in rows:
      emb = json.loads(row["embedding_json"])
      cos_sim = cosine_similarity(query_vector, emb)

      # Keyword overlap boost (hybrid scoring)
      content_lower = row["content"].lower()
      word_hits = sum(1 for w in query_words if w in content_lower)
      keyword_boost = min(0.3, word_hits * 0.05) if query_words else 0.0

      total_score = min(1.0, cos_sim + keyword_boost)

      if total_score >= min_score:
        record = MemoryRecord(
            memory_id=row["memory_id"],
            content=row["content"],
            category=row["category"],
            metadata=json.loads(row["metadata_json"]),
            embedding=emb,
            created_at=row["created_at"],
        )
        results.append(
            MemorySearchResult(
                memory=record,
                similarity_score=round(total_score, 4),
                match_type="hybrid" if keyword_boost > 0 else "vector",
            )
        )

    # Sort descending by score
    results.sort(key=lambda r: r.similarity_score, reverse=True)
    return results[:limit]

  def list_memories(
      self, limit: int = 50, category: Optional[str] = None
  ) -> List[MemoryRecord]:
    """Lists recent memories stored in SQLite."""
    with closing(self._get_connection()) as conn:
      if category:
        cursor = conn.execute(
            "SELECT memory_id, content, category, metadata_json, embedding_json,"
            " created_at FROM semantic_memory WHERE category = ? ORDER BY"
            " created_at DESC LIMIT ?",
            (category, limit),
        )
      else:
        cursor = conn.execute(
            "SELECT memory_id, content, category, metadata_json, embedding_json,"
            " created_at FROM semantic_memory ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
      rows = cursor.fetchall()

      return [
          MemoryRecord(
              memory_id=r["memory_id"],
              content=r["content"],
              category=r["category"],
              metadata=json.loads(r["metadata_json"]),
              embedding=json.loads(r["embedding_json"]),
              created_at=r["created_at"],
          )
          for r in rows
      ]
