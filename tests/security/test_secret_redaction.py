"""Security tests for secret isolation and redaction."""

from security.secrets import SecretRedactor, SecretStore


def test_registered_secret_redaction():
  store = SecretStore()
  store.set_secret("GEMINI_KEY", "AIzaSyD_SecretRealKey1234567890123")
  store.set_secret("GH_PAT", "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789")

  redactor = SecretRedactor(store=store)

  text_with_keys = (
      "Error: Failed to connect with AIzaSyD_SecretRealKey1234567890123 and"
      " ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
  )
  clean_text = redactor.redact_text(text_with_keys)

  assert "AIzaSyD_SecretRealKey" not in clean_text
  assert "ghp_AbCdEfGhIj" not in clean_text
  assert "[REDACTED_SECRET]" in clean_text


def test_secret_patterns_redaction():
  redactor = SecretRedactor(store=SecretStore())

  raw_log = "API_KEY: AIzaSyD9876543210zyxwvutsrqponmlkjih and Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz"
  redacted = redactor.redact_text(raw_log)

  assert "AIzaSyD9876543210" not in redacted
  assert "Bearer" not in redacted or "[REDACTED_SECRET]" in redacted


def test_recursive_data_redaction():
  store = SecretStore()
  store.set_secret("CUSTOM_SECRET", "super_secret_value_999")
  redactor = SecretRedactor(store=store)

  payload = {
      "user": "alice",
      "api_key": "my_hidden_key",
      "details": {
          "token": "ghp_0123456789abcdef0123456789abcdef0123",
          "note": "Here is super_secret_value_999 in text",
      },
      "tags": ["super_secret_value_999", "public"],
  }

  redacted = redactor.redact_data(payload)

  assert redacted["api_key"] == "[REDACTED_SECRET]"
  assert redacted["details"]["token"] == "[REDACTED_SECRET]"
  assert "super_secret_value_999" not in redacted["details"]["note"]
  assert redacted["tags"][0] == "[REDACTED_SECRET]"
  assert redacted["tags"][1] == "public"
