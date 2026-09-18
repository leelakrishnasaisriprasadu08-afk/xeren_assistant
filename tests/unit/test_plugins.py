"""Unit tests for PluginManager and HookRegistry lifecycle hooks."""

import pytest
from core.plugins import BasePlugin, HookRegistry, LifecycleHook, PluginManager


class SampleEchoPlugin(BasePlugin):
  name = "echo_plugin"
  version = "1.0.0"
  description = "A sample test plugin"

  def __init__(self):
    self.triggered_events = []

  def initialize(self, hook_registry: HookRegistry, tool_registry=None):
    hook_registry.register_hook(
        LifecycleHook.ON_REQUEST_START, self.on_start
    )
    hook_registry.register_hook(
        LifecycleHook.ON_RESPONSE_COMPLETE, self.on_complete
    )

  async def on_start(self, query: str):
    self.triggered_events.append(f"start:{query}")

  def on_complete(self, response: str):
    self.triggered_events.append(f"complete:{response}")


@pytest.mark.asyncio
async def test_hook_registry_trigger():
  """Test that HookRegistry dispatches lifecycle events to registered handlers."""
  registry = HookRegistry()
  calls = []

  async def handle_start(q):
    calls.append(f"async_start:{q}")

  def handle_start_sync(q):
    calls.append(f"sync_start:{q}")

  registry.register_hook(LifecycleHook.ON_REQUEST_START, handle_start)
  registry.register_hook(LifecycleHook.ON_REQUEST_START, handle_start_sync)

  await registry.trigger(LifecycleHook.ON_REQUEST_START, "test query")

  assert len(calls) == 2
  assert "async_start:test query" in calls
  assert "sync_start:test query" in calls


@pytest.mark.asyncio
async def test_plugin_manager_registration():
  """Test registering and initializing plugins with PluginManager."""
  hook_registry = HookRegistry()
  manager = PluginManager(hook_registry=hook_registry)

  plugin = SampleEchoPlugin()
  manager.register_plugin(plugin)

  assert "echo_plugin" in manager.loaded_plugins

  # Trigger events
  await hook_registry.trigger(LifecycleHook.ON_REQUEST_START, "Hello Plugin")
  await hook_registry.trigger(LifecycleHook.ON_RESPONSE_COMPLETE, "Done")

  assert len(plugin.triggered_events) == 2
  assert plugin.triggered_events[0] == "start:Hello Plugin"
  assert plugin.triggered_events[1] == "complete:Done"
