"""Unit tests for Phase 9 VisionTool and VisionAgent."""

import pytest
from pathlib import Path
from PIL import Image
from models.provider import MockLLMProvider
from tools.base import Action
from tools.vision_tool import VisionTool


@pytest.fixture
def vision_tool(tmp_path: Path) -> VisionTool:
  mock_llm = MockLLMProvider()
  return VisionTool(llm_provider=mock_llm, screenshot_dir=tmp_path / "screenshots")


@pytest.fixture
def sample_image(tmp_path: Path) -> str:
  img_path = tmp_path / "test_screen.png"
  img = Image.new("RGB", (800, 600), color=(50, 100, 150))
  img.save(str(img_path))
  return str(img_path)


@pytest.mark.asyncio
async def test_vision_analyze_screen(vision_tool: VisionTool):
  action = Action(
      action_id="vis_01",
      tool_name="vision",
      operation="analyze_screen",
      parameters={"prompt": "What application is active?"},
  )
  result = await vision_tool.execute(action)
  assert result.success is True
  assert result.data is not None
  assert "analysis" in result.data
  assert "screenshot_path" in result.data


@pytest.mark.asyncio
async def test_vision_extract_screen_text(vision_tool: VisionTool):
  action = Action(
      action_id="vis_02",
      tool_name="vision",
      operation="extract_screen_text",
      parameters={},
  )
  result = await vision_tool.execute(action)
  assert result.success is True
  assert "analysis" in result.data


@pytest.mark.asyncio
async def test_vision_inspect_image_file(vision_tool: VisionTool, sample_image: str):
  action = Action(
      action_id="vis_03",
      tool_name="vision",
      operation="inspect_image_file",
      parameters={"image_path": sample_image, "prompt": "Describe image colors"},
  )
  result = await vision_tool.execute(action)
  assert result.success is True
  assert result.data["screenshot_path"] == sample_image
