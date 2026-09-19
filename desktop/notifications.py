"""Cross-platform desktop toast notification engine."""

import asyncio
from enum import Enum
import os
import platform
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class NotificationLevel(str, Enum):
  INFO = "INFO"
  SUCCESS = "SUCCESS"
  WARNING = "WARNING"
  ERROR = "ERROR"
  CRITICAL = "CRITICAL"


class NotificationEvent(BaseModel):
  """Structured representation of a desktop notification."""

  id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
  title: str
  message: str
  level: NotificationLevel = NotificationLevel.INFO
  channel: str = "general"
  timestamp: float = Field(default_factory=time.time)
  action_url: Optional[str] = None


class DesktopNotifier:
  """Emits native desktop toast notifications and maintains an in-memory event audit log."""

  _instance: Optional["DesktopNotifier"] = None

  def __init__(self, enabled: bool = True):
    self.enabled = enabled
    self.history: List[NotificationEvent] = []
    self.listeners: List[Callable[[NotificationEvent], None]] = []

  @classmethod
  def get_instance(cls) -> "DesktopNotifier":
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def register_listener(
      self, callback: Callable[[NotificationEvent], None]
  ) -> None:
    """Registers a listener function called on every dispatched notification."""
    self.listeners.append(callback)

  def _send_windows_toast(self, title: str, message: str) -> None:
    """Sends a native Windows toast notification using PowerShell WinRT/Toast API."""
    # Escape quotes for PowerShell script
    clean_title = title.replace('"', '`"')
    clean_msg = message.replace('"', '`"')

    ps_script = f"""
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
        $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $textNodes = $template.GetElementsByTagName("text")
        $textNodes.Item(0).AppendChild($template.CreateTextNode("{clean_title}")) > $null
        $textNodes.Item(1).AppendChild($template.CreateTextNode("{clean_msg}")) > $null
        $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
        $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Xeren Assistant")
        $notifier.Show($toast)
        """
    try:
      subprocess.run(
          ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
          stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL,
          timeout=5,
          check=False,
      )
    except Exception:
      pass

  def notify(
      self,
      title: str,
      message: str,
      level: NotificationLevel = NotificationLevel.INFO,
      channel: str = "general",
      action_url: Optional[str] = None,
  ) -> NotificationEvent:
    """Dispatches a desktop notification synchronously and notifies listeners."""
    event = NotificationEvent(
        title=title,
        message=message,
        level=level,
        channel=channel,
        action_url=action_url,
    )
    self.history.append(event)
    if len(self.history) > 100:
      self.history.pop(0)

    for listener in self.listeners:
      try:
        listener(event)
      except Exception:
        pass

    if self.enabled:
      if platform.system() == "Windows":
        self._send_windows_toast(title, message)

    return event

  async def notify_async(
      self,
      title: str,
      message: str,
      level: NotificationLevel = NotificationLevel.INFO,
      channel: str = "general",
      action_url: Optional[str] = None,
  ) -> NotificationEvent:
    """Non-blocking async notification helper."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, self.notify, title, message, level, channel, action_url
    )

  def get_history(self, limit: int = 50) -> List[NotificationEvent]:
    """Returns recent notification history."""
    return list(reversed(self.history[-limit:]))
