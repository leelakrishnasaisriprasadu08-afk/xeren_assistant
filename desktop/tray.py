"""System Tray Companion for background status monitoring and fast actions."""

import threading
import time
from typing import Callable, Dict, List, Optional
import webbrowser


class SystemTrayCompanion:
  """System tray icon and context menu manager with graceful fallback."""

  def __init__(
      self,
      app_name: str = "Xeren Assistant",
      dashboard_url: str = "http://127.0.0.1:8000",
      on_exit: Optional[Callable[[], None]] = None,
  ):
    self.app_name = app_name
    self.dashboard_url = dashboard_url
    self.on_exit = on_exit
    self.status: str = "Idle"
    self._is_running = False
    self._tray_icon = None

  def set_status(self, status: str) -> None:
    """Updates active tray status (Idle, Busy, Error)."""
    self.status = status
    if self._tray_icon:
      try:
        self._tray_icon.title = f"{self.app_name} — {self.status}"
      except Exception:
        pass

  def _open_dashboard(self) -> None:
    try:
      webbrowser.open(self.dashboard_url)
    except Exception:
      pass

  def _open_swarm(self) -> None:
    try:
      webbrowser.open(f"{self.dashboard_url}/#swarm")
    except Exception:
      pass

  def _open_codebase(self) -> None:
    try:
      webbrowser.open(f"{self.dashboard_url}/#codebase")
    except Exception:
      pass

  def _handle_exit(self) -> None:
    self.stop()
    if self.on_exit:
      self.on_exit()

  def run_in_background(self) -> None:
    """Starts the system tray in a background thread."""
    if self._is_running:
      return
    self._is_running = True

    try:
      import pystray
      from PIL import Image, ImageDraw

      # Generate a programmatic icon
      width, height = 64, 64
      image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
      draw = ImageDraw.Draw(image)
      draw.ellipse([4, 4, 60, 60], fill=(0, 240, 255, 255))
      draw.text((22, 18), "X", fill=(0, 0, 0, 255))

      menu = pystray.Menu(
          pystray.MenuItem("💬 Open Dashboard", self._open_dashboard),
          pystray.MenuItem("🤖 Multi-Agent Swarm", self._open_swarm),
          pystray.MenuItem("💻 Codebase & Patch Studio", self._open_codebase),
          pystray.Menu.SEPARATOR,
          pystray.MenuItem("❌ Exit Xeren Daemon", self._handle_exit),
      )

      self._tray_icon = pystray.Icon(
          self.app_name, image, f"{self.app_name} — {self.status}", menu
      )

      threading.Thread(target=self._tray_icon.run, daemon=True).start()

    except Exception:
      # Fallback headless loop when GUI / pystray display unavailable
      pass

  def stop(self) -> None:
    """Stops and removes the tray icon."""
    self._is_running = False
    if self._tray_icon:
      try:
        self._tray_icon.stop()
      except Exception:
        pass
      self._tray_icon = None

  @property
  def is_running(self) -> bool:
    return self._is_running
