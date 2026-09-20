"""Unit tests for Universal DeviceTool."""

import pytest
from pathlib import Path
from tools.base import Action
from tools.device_tool import DeviceTool


@pytest.fixture
def device_tool(tmp_path: Path) -> DeviceTool:
  return DeviceTool(screenshot_dir=tmp_path / "screenshots")


@pytest.mark.asyncio
async def test_device_server_health_check(device_tool: DeviceTool):
  action = Action(
      action_id="act_srv_01",
      tool_name="device",
      operation="server_health_check",
      parameters={"ports": [8000, 3000, 5000]},
  )
  result = await device_tool.execute(action)
  assert result.success is True
  assert result.data is not None
  assert "health_score" in result.data
  assert "overall_status" in result.data
  assert result.data["overall_status"] in ["HEALTHY", "DEGRADED", "CRITICAL"]
  assert "cpu" in result.data
  assert "memory" in result.data
  assert "uptime" in result.data
  assert "listening_services" in result.data


@pytest.mark.asyncio
async def test_device_check_network_ports(device_tool: DeviceTool):
  action = Action(
      action_id="act_net_01",
      tool_name="device",
      operation="check_network_ports",
      parameters={},
  )
  result = await device_tool.execute(action)
  assert result.success is True
  assert result.data is not None
  assert "hostname" in result.data


@pytest.mark.asyncio
async def test_device_get_system_info(device_tool: DeviceTool):
  action = Action(
      action_id="act_01",
      tool_name="device",
      operation="get_system_info",
      parameters={},
  )
  result = await device_tool.execute(action)
  assert result.success is True
  assert result.data is not None
  assert "platform" in result.data
  assert "cpu" in result.data
  assert "memory" in result.data


@pytest.mark.asyncio
async def test_device_list_processes(device_tool: DeviceTool):
  action = Action(
      action_id="act_02",
      tool_name="device",
      operation="list_processes",
      parameters={"limit": 5, "sort_by": "memory"},
  )
  result = await device_tool.execute(action)
  assert result.success is True
  assert isinstance(result.data, list)
  if len(result.data) > 0:
    first_proc = result.data[0]
    assert "pid" in first_proc
    assert "name" in first_proc
    assert "memory_mb" in first_proc


@pytest.mark.asyncio
async def test_device_clipboard(device_tool: DeviceTool):
  # Set clipboard
  test_phrase = "Xeren Assistant Device Automation Test Phrase"
  action_set = Action(
      action_id="act_03",
      tool_name="device",
      operation="set_clipboard",
      parameters={"text": test_phrase},
  )
  res_set = await device_tool.execute(action_set)
  assert res_set.success is True

  # Get clipboard
  action_get = Action(
      action_id="act_04",
      tool_name="device",
      operation="get_clipboard",
      parameters={},
  )
  res_get = await device_tool.execute(action_get)
  assert res_get.success is True
  assert "clipboard_text" in res_get.data


@pytest.mark.asyncio
async def test_device_screenshot(device_tool: DeviceTool, tmp_path: Path):
  out_path = str(tmp_path / "custom_screenshot.png")
  action = Action(
      action_id="act_05",
      tool_name="device",
      operation="capture_screenshot",
      parameters={"output_path": out_path},
  )
  result = await device_tool.execute(action)
  assert result.success is True
  assert "file_path" in result.data
  assert Path(out_path).exists()


@pytest.mark.asyncio
async def test_device_windows(device_tool: DeviceTool):
  action_active = Action(
      action_id="act_06",
      tool_name="device",
      operation="get_active_window",
      parameters={},
  )
  res_active = await device_tool.execute(action_active)
  assert res_active.success is True
  assert "title" in res_active.data

  action_list = Action(
      action_id="act_07",
      tool_name="device",
      operation="list_windows",
      parameters={},
  )
  res_list = await device_tool.execute(action_list)
  assert res_list.success is True
  assert isinstance(res_list.data, list)


@pytest.mark.asyncio
async def test_device_audio_and_lock(device_tool: DeviceTool):
  action_mute = Action(
      action_id="act_08",
      tool_name="device",
      operation="mute_volume",
      parameters={},
  )
  res_mute = await device_tool.execute(action_mute)
  assert res_mute.success is True

  action_vol = Action(
      action_id="act_09",
      tool_name="device",
      operation="set_volume",
      parameters={"level": 75},
  )
  res_vol = await device_tool.execute(action_vol)
  assert res_vol.success is True
  assert res_vol.data["level"] == 75
