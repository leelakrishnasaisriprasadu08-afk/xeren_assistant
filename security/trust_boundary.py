"""Trust Boundary layer isolating untrusted external data and preventing prompt injection authority."""

import html
import re
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from .secrets import SecretRedactor


class UntrustedData(BaseModel):
  """Container for data retrieved from external sources.

  Explicitly carries NO instruction authority over the assistant, planner,
  controller, or tools.
  """

  source: str = Field(
      description="Origin of the data (e.g. 'web_search', 'github_issue')"
  )
  raw_content: str = Field(description="Sanitized data payload")
  metadata: Dict[str, Any] = Field(default_factory=dict)
  is_trusted: bool = Field(
      default=False,
      description="Always False for external data; prevents execution authority",
  )

  def format_for_context(self) -> str:
    """Formats untrusted content inside a strict data container.

    This ensures the LLM interprets it solely as passive text, never as system
    instructions.
    """
    return (
        f'<untrusted_external_content source="{html.escape(self.source)}">\n'
        f"{self.raw_content}\n"
        f"</untrusted_external_content>"
    )


class TrustBoundary:
  """Sanitizes, isolates, and wraps external inputs to maintain trust integrity."""

  # Remove ANSI escape sequences, null bytes, and dangerous Unicode formatting
  CONTROL_CHAR_REGEX = re.compile(
      r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F\u202A-\u202E\u2066-\u2069]"
  )

  def __init__(self, redactor: Optional[SecretRedactor] = None):
    self.redactor = redactor or SecretRedactor()

  def sanitize_text(self, text: str) -> str:
    """Sanitizes text by stripping control sequences, redacting secrets, and normalizing whitespace."""
    if not text or not isinstance(text, str):
      return ""

    # Strip control chars
    clean_text = self.CONTROL_CHAR_REGEX.sub("", text)

    # Redact any registered or pattern secrets
    clean_text = self.redactor.redact_text(clean_text)

    return clean_text.strip()

  def wrap_external_data(
      self, source: str, content: Any, metadata: Optional[Dict[str, Any]] = None
  ) -> UntrustedData:
    """Wraps external tool outputs in an UntrustedData container with zero instruction authority."""
    if isinstance(content, (dict, list)):
      import json

      text_representation = json.dumps(content, indent=2)
    else:
      text_representation = str(content)

    sanitized = self.sanitize_text(text_representation)

    return UntrustedData(
        source=source,
        raw_content=sanitized,
        metadata=metadata or {},
        is_trusted=False,
    )
