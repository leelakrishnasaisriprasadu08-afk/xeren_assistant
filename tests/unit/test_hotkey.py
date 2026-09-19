"""Unit tests for GlobalHotkeyListener parsing and triggers."""

import pytest
from desktop.hotkey import GlobalHotkeyListener


def test_hotkey_shortcut_parsing():
  listener = GlobalHotkeyListener(shortcut="ctrl+shift+x")
  modifiers, vk_code = listener._parse_shortcut_windows()

  assert modifiers & GlobalHotkeyListener.MOD_CONTROL
  assert modifiers & GlobalHotkeyListener.MOD_SHIFT
  assert vk_code == ord("X")


def test_hotkey_alt_space_parsing():
  listener = GlobalHotkeyListener(shortcut="alt+space")
  modifiers, vk_code = listener._parse_shortcut_windows()

  assert modifiers & GlobalHotkeyListener.MOD_ALT
  assert vk_code == 0x20  # SPACE key code


def test_hotkey_callback_trigger():
  triggered = []

  def custom_callback():
    triggered.append(True)

  listener = GlobalHotkeyListener(
      shortcut="ctrl+shift+z", callback=custom_callback
  )
  listener.callback()
  assert len(triggered) == 1
