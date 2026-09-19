"""Integration tests for Phase 7 Desktop Daemon and Notification workflows."""

from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from app.api import create_app
from core.assistant import XerenAssistant
from desktop.daemon import DesktopDaemon
from desktop.notifications import DesktopNotifier, NotificationLevel


@pytest.fixture
def client(tmp_path: Path):
  from config.settings import Settings

  settings = Settings(workspace_root=tmp_path, db_path=tmp_path / "test.sqlite")
  assistant = XerenAssistant(settings=settings)
  app = create_app(assistant)
  return TestClient(app)


def test_notification_and_daemon_integration(client: TestClient):
  notifier = DesktopNotifier.get_instance()
  notifier.enabled = False  # Avoid OS popup in test run

  evt = notifier.notify(
      title="Security Alert",
      message="File write requested for index.html",
      level=NotificationLevel.WARNING,
      channel="security",
  )

  assert evt.title == "Security Alert"
  assert evt.level == NotificationLevel.WARNING

  history = notifier.get_history(limit=5)
  assert len(history) >= 1
  assert history[0].title == "Security Alert"

  # Test daemon status endpoint / healthcheck
  res = client.get("/health")
  assert res.status_code == 200
  data = res.json()
  assert data["status"] == "ok"
