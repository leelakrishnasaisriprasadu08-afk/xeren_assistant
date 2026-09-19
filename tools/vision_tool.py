from pathlib import Path
import time
from typing import Any, Dict, List, Optional
from models.base import BaseLLMProvider
from .base import Action, BaseTool, ToolResult


class VisionTool(BaseTool):
  """Tool enabling screen vision, image inspection, and visual error diagnostics."""

  def __init__(
      self,
      llm_provider: Optional[BaseLLMProvider] = None,
      screenshot_dir: Optional[Path] = None,
  ):
    from agents.vision_agent import VisionAgent

    self.agent = VisionAgent(
        llm_provider=llm_provider, screenshot_dir=screenshot_dir
    )


  @property
  def name(self) -> str:
    return "vision"

  @property
  def description(self) -> str:
    return (
        "Multi-modal vision tool for inspecting desktop screens, analyzing UI"
        " layouts, extracting visible text/errors, and answering questions about"
        " visual images."
    )

  @property
  def supported_operations(self) -> List[str]:
    return [
        "analyze_screen",
        "extract_screen_text",
        "inspect_image_file",
    ]

  async def execute(self, action: Action) -> ToolResult:
    start_time = time.perf_counter()
    op = action.operation.lower()
    params = action.parameters or {}

    try:
      if op == "analyze_screen":
        prompt = params.get("prompt") or params.get("query") or "Analyze the active screen and describe the visible applications, layout, and contents."
        image_path = params.get("image_path") or params.get("path")
        data = await self.agent.analyze_screen(prompt=prompt, image_path=image_path)

      elif op == "extract_screen_text":
        image_path = params.get("image_path") or params.get("path")
        data = await self.agent.extract_screen_text(image_path=image_path)

      elif op == "inspect_image_file":
        image_path = params.get("image_path") or params.get("path")
        if not image_path:
          raise ValueError("Parameter 'image_path' is required for inspect_image_file.")
        prompt = params.get("prompt") or "Inspect and describe this image."
        data = await self.agent.analyze_screen(prompt=prompt, image_path=image_path)

      else:
        raise ValueError(f"Unsupported operation '{op}' for tool '{self.name}'")

      elapsed = (time.perf_counter() - start_time) * 1000
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=True,
          data=data,
          execution_time_ms=elapsed,
      )
    except Exception as e:
      elapsed = (time.perf_counter() - start_time) * 1000
      return ToolResult(
          action_id=action.action_id,
          tool_name=self.name,
          operation=action.operation,
          success=False,
          error=str(e),
          execution_time_ms=elapsed,
      )
