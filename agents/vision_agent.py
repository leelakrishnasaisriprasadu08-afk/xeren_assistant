"""Multi-modal Vision Agent for screen understanding, visual grounding, and OCR diagnostics."""

import asyncio
from datetime import datetime, timezone
import io
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from models.base import BaseLLMProvider
from models.provider import get_default_llm_provider

try:
  from PIL import Image, ImageGrab
except ImportError:
  Image = None
  ImageGrab = None


class VisionAgent:
  """Specialized autonomous agent for screen understanding and image analysis."""

  def __init__(
      self,
      llm_provider: Optional[BaseLLMProvider] = None,
      screenshot_dir: Optional[Path] = None,
  ):
    self.llm_provider = llm_provider or get_default_llm_provider()
    self.screenshot_dir = (screenshot_dir or Path("data/screenshots")).resolve()
    self.screenshot_dir.mkdir(parents=True, exist_ok=True)

  def _capture_screen_bytes(self, output_path: Optional[str] = None) -> tuple[bytes, str]:
    """Captures current screen and returns PNG bytes and saved file path."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = Path(output_path) if output_path else self.screenshot_dir / f"vision_{timestamp}.png"
    out_file.parent.mkdir(parents=True, exist_ok=True)

    if ImageGrab:
      try:
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img.save(str(out_file), format="PNG")
        return buf.getvalue(), str(out_file)
      except Exception:
        pass

    # Canvas fallback
    if Image:
      img = Image.new("RGB", (1920, 1080), color=(25, 28, 36))
      buf = io.BytesIO()
      img.save(buf, format="PNG")
      img.save(str(out_file), format="PNG")
      return buf.getvalue(), str(out_file)

    return b"", str(out_file)

  async def analyze_screen(
      self,
      prompt: str = "Analyze the active screen and describe the visible applications, layout, and contents.",
      image_path: Optional[str] = None,
  ) -> Dict[str, Any]:
    """Analyzes the current desktop screen or specified image with multimodal vision LLM."""
    if image_path and Path(image_path).exists():
      img_file = Path(image_path)
      img_bytes = img_file.read_bytes()
      saved_path = str(img_file)
    else:
      img_bytes, saved_path = self._capture_screen_bytes()

    system_instruction = (
        "You are the Vision Analysis Agent for Xeren Assistant. Your job is to"
        " inspect desktop screens and images, diagnose errors, identify"
        " active application windows, find actionable UI buttons/elements,"
        " and provide clear, structured technical summaries."
    )

    response = await self.llm_provider.generate_vision(
        prompt=prompt,
        image_bytes=img_bytes,
        mime_type="image/png",
        system_instruction=system_instruction,
    )

    return {
        "analysis": response.text,
        "screenshot_path": saved_path,
        "prompt": prompt,
        "model": response.model_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

  async def extract_screen_text(
      self, image_path: Optional[str] = None
  ) -> Dict[str, Any]:
    """Extracts all visible text, error messages, and headings from the screen."""
    prompt = (
        "Extract all readable text, titles, logs, code snippets, and error"
        " messages visible on this screen. Group them by window/section and"
        " highlight any error alerts."
    )
    return await self.analyze_screen(prompt=prompt, image_path=image_path)
