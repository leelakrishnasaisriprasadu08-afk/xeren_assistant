"""Dynamic Plugin Architecture and Lifecycle Hook Subsystem."""

import asyncio
from enum import Enum
import importlib.util
import inspect
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from tools.base import BaseTool
from tools.registry import ToolRegistry


class LifecycleHook(str, Enum):
  ON_REQUEST_START = "on_request_start"
  ON_ACTION_PLANNED = "on_action_planned"
  ON_TOOL_EXECUTED = "on_tool_executed"
  ON_RESPONSE_COMPLETE = "on_response_complete"


class HookRegistry:
  """Manages registration and execution of lifecycle event hooks."""

  def __init__(self):
    self._hooks: Dict[LifecycleHook, List[Callable[..., Any]]] = {
        h: [] for h in LifecycleHook
    }

  def register_hook(
      self, event: LifecycleHook, callback: Callable[..., Any]
  ) -> None:
    """Subscribes a callback to a lifecycle event."""
    self._hooks[event].append(callback)

  async def trigger(self, event: LifecycleHook, *args: Any, **kwargs: Any) -> None:
    """Executes all callbacks subscribed to the event."""
    callbacks = self._hooks.get(event, [])
    for cb in callbacks:
      try:
        if inspect.iscoroutinefunction(cb):
          await cb(*args, **kwargs)
        else:
          cb(*args, **kwargs)
      except Exception:
        pass  # Ensure hook failures do not crash the core pipeline


class BasePlugin:
  """Base class for all Xeren Assistant plugins."""

  name: str = "base_plugin"
  version: str = "1.0.0"
  description: str = ""

  def initialize(
      self,
      hook_registry: HookRegistry,
      tool_registry: Optional[ToolRegistry] = None,
  ) -> None:
    """Hook invoked when the plugin is loaded into the assistant."""
    pass


class PluginManager:
  """Discovers, validates, and dynamically registers custom extensions from plugins directory."""

  def __init__(
      self,
      plugins_dir: Optional[Path] = None,
      hook_registry: Optional[HookRegistry] = None,
      tool_registry: Optional[ToolRegistry] = None,
  ):
    self.plugins_dir = (plugins_dir or Path("plugins")).resolve()
    self.plugins_dir.mkdir(parents=True, exist_ok=True)
    self.hook_registry = hook_registry or HookRegistry()
    self.tool_registry = tool_registry
    self.loaded_plugins: Dict[str, BasePlugin] = {}

  def register_plugin(self, plugin: BasePlugin) -> None:
    """Manually registers an initialized plugin instance."""
    plugin.initialize(
        hook_registry=self.hook_registry, tool_registry=self.tool_registry
    )
    self.loaded_plugins[plugin.name] = plugin

  def discover_and_load(self) -> List[str]:
    """Scans the plugins directory for Python plugin definitions and initializes them."""
    loaded_names = []
    if not self.plugins_dir.exists():
      return loaded_names

    for file_path in self.plugins_dir.glob("*.py"):
      if file_path.name.startswith("__"):
        continue

      module_name = f"xeren_plugin_{file_path.stem}"
      spec = importlib.util.spec_from_file_location(module_name, str(file_path))
      if spec and spec.loader:
        try:
          mod = importlib.util.module_from_spec(spec)
          spec.loader.exec_module(mod)

          # Find plugin class inside module
          for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BasePlugin)
                and attr is not BasePlugin
            ):
              plugin_instance = attr()
              self.register_plugin(plugin_instance)
              loaded_names.append(plugin_instance.name)
        except Exception:
          pass

    return loaded_names
