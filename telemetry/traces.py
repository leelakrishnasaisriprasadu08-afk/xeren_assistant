"""Structured execution tracing for Xeren Assistant."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from security.secrets import SecretRedactor


class TraceRecord(BaseModel):
  """Comprehensive trace record capturing full execution lifecycle."""

  trace_id: str
  timestamp: str = Field(
      default_factory=lambda: datetime.now(timezone.utc).isoformat()
  )
  user_request: str
  intent: Optional[Dict[str, Any]] = None
  plan: List[Dict[str, Any]] = Field(default_factory=list)
  permission_decisions: List[Dict[str, Any]] = Field(default_factory=list)
  tool_executions: List[Dict[str, Any]] = Field(default_factory=list)
  verification_results: List[Dict[str, Any]] = Field(default_factory=list)
  final_response: str = ""
  total_duration_ms: float = 0.0
  success: bool = True
  error: Optional[str] = None


class TraceLogger:
  """Appends structured trace records to a JSONL log file with secret redaction."""

  def __init__(
      self,
      traces_dir: Optional[Path] = None,
      redactor: Optional[SecretRedactor] = None,
  ):
    self.traces_dir = (traces_dir or Path("traces")).resolve()
    self.traces_dir.mkdir(parents=True, exist_ok=True)
    self.log_file = self.traces_dir / "traces.jsonl"
    self.redactor = redactor or SecretRedactor()

  def log_trace(self, record: TraceRecord) -> None:
    """Serializes, redacts, and persists trace record to JSONL."""
    try:
      raw_dict = record.model_dump()
      redacted_dict = self.redactor.redact_data(raw_dict)
      line = json.dumps(redacted_dict) + "\n"

      with open(self.log_file, "a", encoding="utf-8") as f:
        f.write(line)
    except Exception:
      pass

  def list_traces(self, limit: int = 20) -> List[TraceRecord]:
    """Reads recent trace records from JSONL."""
    if not self.log_file.exists():
      return []
    records: List[TraceRecord] = []
    try:
      with open(self.log_file, "r", encoding="utf-8") as f:
        for line in f:
          if line.strip():
            try:
              data = json.loads(line.strip())
              records.append(TraceRecord(**data))
            except Exception:
              pass
      return list(reversed(records))[:limit]
    except Exception:
      return []

  def get_trace(self, trace_id: str) -> Optional[TraceRecord]:
    """Finds a specific trace by trace_id."""
    if not self.log_file.exists():
      return None
    try:
      with open(self.log_file, "r", encoding="utf-8") as f:
        for line in f:
          if line.strip():
            try:
              data = json.loads(line.strip())
              if data.get("trace_id") == trace_id:
                return TraceRecord(**data)
            except Exception:
              pass
      return None
    except Exception:
      return None
