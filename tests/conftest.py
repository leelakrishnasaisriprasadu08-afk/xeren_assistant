"""Test suite configuration and shared fixtures for Xeren Assistant."""

import tempfile
from pathlib import Path
import pytest

from config.settings import Settings
from security.permission_gate import PermissionGate
from security.secrets import SecretRedactor, SecretStore
from security.trust_boundary import TrustBoundary


@pytest.fixture
def temp_workspace():
  """Creates a temporary workspace sandbox directory for tests."""
  with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
    workspace_path = Path(tmpdir).resolve()
    # Create some dummy files
    (workspace_path / "src").mkdir()
    (workspace_path / "src" / "main.py").write_text(
        "print('hello xeren')", encoding="utf-8"
    )
    (workspace_path / "README.md").write_text(
        "# Xeren Workspace", encoding="utf-8"
    )
    yield workspace_path


@pytest.fixture
def test_settings(temp_workspace):
  """Provides isolated test settings pointing to temporary directory."""
  return Settings(
      workspace_root=temp_workspace,
      db_path=temp_workspace / "test.sqlite",
      traces_dir=temp_workspace / "traces",
      preferences_path=temp_workspace / "preferences.yaml",
      gemini_api_key="test_gemini_key_mock",
      github_token="test_gh_token_mock",
  )


@pytest.fixture
def permission_gate(temp_workspace):
  """Returns a configured PermissionGate locked to temp_workspace."""
  return PermissionGate(workspace_root=temp_workspace)


@pytest.fixture
def secret_store():
  """Provides a fresh isolated SecretStore."""
  store = SecretStore()
  store.clear()
  return store


@pytest.fixture
def trust_boundary(secret_store):
  """Provides a TrustBoundary using isolated secret store."""
  redactor = SecretRedactor(store=secret_store)
  return TrustBoundary(redactor=redactor)
