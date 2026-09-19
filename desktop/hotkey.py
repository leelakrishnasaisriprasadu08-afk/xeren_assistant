"""Global OS Keyboard Shortcut Listener for fast AI assistant invocation."""

import ctypes
import os
import platform
import threading
import time
from typing import Callable, Optional
import webbrowser


class GlobalHotkeyListener:
  """Listens for global system keyboard combinations to invoke Xeren Assistant."""

  # Default hotkey: Ctrl + Shift + X (MOD_CONTROL | MOD_SHIFT, 0x58 for 'X')
  MOD_ALT = 0x0001
  MOD_CONTROL = 0x0002
  MOD_SHIFT = 0x0004
  MOD_WIN = 0x0008

  def __init__(
      self,
      shortcut: str = "ctrl+shift+x",
      callback: Optional[Callable[[], None]] = None,
      dashboard_url: str = "http://127.0.0.1:8000",
  ):
    self.shortcut = shortcut.lower()
    self.callback = callback or self._default_action
    self.dashboard_url = dashboard_url
    self._is_running = False
    self._thread: Optional[threading.Thread] = None

  def _default_action(self) -> None:
    """Default hotkey action: open browser dashboard."""
    try:
      webbrowser.open(self.dashboard_url)
    except Exception:
      pass

  def _parse_shortcut_windows(self) -> tuple[int, int]:
    """Parses hotkey string into Windows modifiers and virtual key code."""
    modifiers = 0
    key_code = 0x58  # Default 'X'

    parts = self.shortcut.split("+")
    for part in parts[:-1]:
      p = part.strip()
      if p in ["ctrl", "control"]:
        modifiers |= self.MOD_CONTROL
      elif p in ["shift"]:
        modifiers |= self.MOD_SHIFT
      elif p in ["alt"]:
        modifiers |= self.MOD_ALT
      elif p in ["win", "windows", "cmd"]:
        modifiers |= self.MOD_WIN

    final_key = parts[-1].strip().upper()
    if len(final_key) == 1:
      key_code = ord(final_key)
    elif final_key == "SPACE":
      key_code = 0x20

    return modifiers, key_code

  def _windows_listener_loop(self) -> None:
    """Windows ctypes message loop registering RegisterHotKey."""
    if platform.system() != "Windows":
      return

    user32 = ctypes.windll.user32
    modifiers, vk_code = self._parse_shortcut_windows()
    HOTKEY_ID = 101

    if not user32.RegisterHotKey(None, HOTKEY_ID, modifiers, vk_code):
      return

    self._is_running = True
    msg = ctypes.wintypes.MSG()

    try:
      while self._is_running:
        # Non-blocking or timed message retrieval
        if user32.PeekMessageW(
            ctypes.byref(msg), None, 0, 0, 0x0001
        ):  # PM_REMOVE
          if msg.message == 0x0312:  # WM_HOTKEY
            if msg.wParam == HOTKEY_ID and self.callback:
              self.callback()
          user32.TranslateMessage(ctypes.byref(msg))
          user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.05)
    finally:
      user32.UnregisterHotKey(None, HOTKEY_ID)
      self._is_running = False

  def start(self) -> None:
    """Starts the background hotkey listener thread."""
    if self._is_running:
      return

    if platform.system() == "Windows":
      self._thread = threading.Thread(
          target=self._windows_listener_loop, daemon=True
      )
      self._thread.start()
      self._is_running = True

  def stop(self) -> None:
    """Stops the hotkey listener thread."""
    self._is_running = False
    if self._thread and self._thread.is_alive():
      self._thread.join(timeout=1.0)

  @property
  def is_active(self) -> bool:
    return self._is_running
