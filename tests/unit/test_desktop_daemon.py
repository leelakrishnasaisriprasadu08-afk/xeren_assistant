"""Unit tests for DesktopDaemon lifecycle and status management."""

import pytest
from desktop.daemon import DaemonStatus, DesktopDaemon


def test_desktop_daemon_lifecycle():
  daemon = DesktopDaemon(host="127.0.0.1", port=8999)
  assert daemon.status == DaemonStatus.STOPPED

  # Start without server thread for unit testing
  status = daemon.start(run_server=False)
  assert status["status"] == DaemonStatus.RUNNING.value
  assert "127.0.0.1:8999" in status["dashboard_url"]

  # Stop daemon
  stop_status = daemon.stop()
  assert stop_status["status"] == DaemonStatus.STOPPED.value
