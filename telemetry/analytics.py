"""Basic telemetry and usage counters."""

from collections import defaultdict
from typing import Any, Dict


class AnalyticsTracker:
  """In-memory telemetry tracker for task performance and reliability metrics."""

  def __init__(self):
    self.total_requests: int = 0
    self.successful_requests: int = 0
    self.failed_requests: int = 0
    self.tool_usage_counts: Dict[str, int] = defaultdict(int)
    self.intent_counts: Dict[str, int] = defaultdict(int)

  def record_request(
      self, intent_type: str, success: bool, tools_used: list[str]
  ) -> None:
    self.total_requests += 1
    if success:
      self.successful_requests += 1
    else:
      self.failed_requests += 1

    self.intent_counts[intent_type] += 1
    for tool in tools_used:
      self.tool_usage_counts[tool] += 1

  def get_summary(self) -> Dict[str, Any]:
    rate = (
        (self.successful_requests / self.total_requests * 100)
        if self.total_requests > 0
        else 100.0
    )
    return {
        "total_requests": self.total_requests,
        "successful_requests": self.successful_requests,
        "failed_requests": self.failed_requests,
        "success_rate_percent": round(rate, 2),
        "tool_usage": dict(self.tool_usage_counts),
        "intents": dict(self.intent_counts),
    }
