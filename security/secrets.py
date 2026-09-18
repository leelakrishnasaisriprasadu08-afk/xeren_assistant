"""Secret isolation and redaction utilities."""

import re
from typing import Any, Dict, List, Optional, Set


class SecretStore:
  """In-memory secure store for API keys and credentials.

  Ensures secrets are not kept in ordinary configuration dictionaries or
  serialized outputs.
  """

  _instance: Optional["SecretStore"] = None

  def __init__(self):
    self._secrets: Dict[str, str] = {}
    self._registered_values: Set[str] = set()

  @classmethod
  def get_instance(cls) -> "SecretStore":
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def set_secret(self, key: str, value: Optional[str]) -> None:
    if value and value.strip():
      clean_val = value.strip()
      self._secrets[key] = clean_val
      if len(clean_val) >= 4:  # Avoid registering trivially short strings
        self._registered_values.add(clean_val)

  def get_secret(self, key: str) -> Optional[str]:
    return self._secrets.get(key)

  def get_registered_secrets(self) -> Set[str]:
    return set(self._registered_values)

  def clear(self) -> None:
    self._secrets.clear()
    self._registered_values.clear()


class SecretRedactor:
  """Scans text and nested data structures to redact sensitive credentials."""

  # Common token and key regex signatures
  SECRET_PATTERNS = [
      re.compile(r"ghp_[A-Za-z0-9_]{36,255}"),  # GitHub Personal Access Token
      re.compile(
          r"github_pat_[A-Za-z0-9_]{22}_[A-Za-z0-9_]{59}"
      ),  # Fine-grained PAT
      re.compile(r"AIza[0-9A-Za-z-_]{35}"),  # Google/Gemini API Key
      re.compile(
          r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE
      ),  # Authorization Bearer
      re.compile(
          r"(?i)(api[_-]?key|secret|token|password)[\s:=]+['\"]?([A-Za-z0-9\-_]{8,})['\"]?"
      ),
  ]

  def __init__(self, store: Optional[SecretStore] = None):
    self.store = store or SecretStore.get_instance()

  def redact_text(self, text: str) -> str:
    """Scrubs all registered secrets and known secret patterns from a string."""
    if not text or not isinstance(text, str):
      return text

    redacted = text

    # Redact explicitly registered secret values first
    for secret in self.store.get_registered_secrets():
      if secret in redacted:
        redacted = redacted.replace(secret, "[REDACTED_SECRET]")

    # Redact using regex pattern signatures
    for pattern in self.SECRET_PATTERNS:
      # If pattern has groups (like key-value regex), replace the value group
      if pattern.groups > 1:
        redacted = pattern.sub(r"\1: [REDACTED_SECRET]", redacted)
      else:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)

    return redacted

  def redact_data(self, data: Any) -> Any:
    """Recursively redacts dictionary, list, or string values."""
    if isinstance(data, str):
      return self.redact_text(data)
    elif isinstance(data, dict):
      redacted_dict = {}
      for k, v in data.items():
        # Mask sensitive keys directly
        if any(
            sens in str(k).lower()
            for sens in ["token", "secret", "password", "api_key", "key"]
        ):
          redacted_dict[k] = "[REDACTED_SECRET]"
        else:
          redacted_dict[k] = self.redact_data(v)
      return redacted_dict
    elif isinstance(data, list):
      return [self.redact_data(item) for item in data]
    elif isinstance(data, tuple):
      return tuple(self.redact_data(item) for item in data)
    return data


# Alias for backward/forward compatibility
RedactionEngine = SecretRedactor
