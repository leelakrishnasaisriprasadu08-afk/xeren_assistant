"""Desktop Daemon Manager orchestrating background server, hotkeys, tray, and notifications."""

import asyncio
from enum import Enum
import threading
import time
from typing import Any, Dict, Optional
import uvicorn
from config.settings import Settings, get_settings
from core.assistant import XerenAssistant
from .hotkey import GlobalHotkeyListener
from .notifications import DesktopNotifier, NotificationLevel
from .tray import SystemTrayCompanion


class DaemonStatus(str, Enum):
  STOPPED = "STOPPED"
  STARTING = "STARTING"
  RUNNING = "RUNNING"
  ERROR = "ERROR"


class DesktopDaemon:
  """Central background service manager coordinating system tray, hotkeys, and notifications."""

  def __init__(
      self,
      settings: Optional[Settings] = None,
      assistant: Optional[XerenAssistant] = None,
      host: str = "127.0.0.1",
      port: int = 8000,
  ):
    self.settings = settings or get_settings()
    self.assistant = assistant or XerenAssistant(settings=self.settings)
    self.host = host
    self.port = port
    self.status = DaemonStatus.STOPPED
    self.dashboard_url = f"http://{host}:{port}"

    self.notifier = DesktopNotifier.get_instance()
    self.tray = SystemTrayCompanion(
        app_name=self.settings.app_name,
        dashboard_url=self.dashboard_url,
        on_exit=self.stop,
    )
    self.hotkey_listener = GlobalHotkeyListener(
        shortcut="ctrl+shift+x",
        callback=self.tray._open_dashboard,
        dashboard_url=self.dashboard_url,
    )
    self._server_thread: Optional[threading.Thread] = None
    self._server: Optional[uvicorn.Server] = None

  def start_server_thread(self) -> None:
    """Launches the FastAPI API & Web Dashboard in a daemon thread."""
    from app.api import create_app

    app = create_app(assistant=self.assistant)
    config = uvicorn.Config(
        app=app, host=self.host, port=self.port, log_level="warning"
    )
    self._server = uvicorn.Server(config)

    def run_server():
      self._server.run()

    self._server_thread = threading.Thread(target=run_server, daemon=True)
    self._server_thread.start()

  def start(self, run_server: bool = True) -> Dict[str, Any]:
    """Starts all daemon background services."""
    if self.status == DaemonStatus.RUNNING:
      return self.get_status()

    self.status = DaemonStatus.STARTING

    # 1. Start Server if requested
    if run_server:
      self.start_server_thread()

    # 2. Start Global Hotkey Listener
    self.hotkey_listener.start()

    # 3. Start System Tray Icon
    self.tray.run_in_background()

    self.status = DaemonStatus.RUNNING

    # 4. Dispatch initial notification
    self.notifier.notify(
        title="Xeren Assistant Active",
        message="Background daemon running. Press Ctrl+Shift+X for instant AI.",
        level=NotificationLevel.SUCCESS,
        channel="daemon",
        action_url=self.dashboard_url,
    )

    return self.get_status()

  def stop(self) -> Dict[str, Any]:
    """Gracefully shuts down all daemon services."""
    self.status = DaemonStatus.STOPPED
    self.hotkey_listener.stop()
    self.tray.stop()
    if self._server:
      self._server.should_exit = True
    return self.get_status()

  def get_status(self) -> Dict[str, Any]:
    """Returns runtime telemetry for the desktop daemon."""
    return {
        "status": self.status.value,
        "dashboard_url": self.dashboard_url,
        "hotkey_active": self.hotkey_listener.is_active,
        "tray_running": self.tray.is_running,
        "notifications_count": len(self.notifier.history),
    }
