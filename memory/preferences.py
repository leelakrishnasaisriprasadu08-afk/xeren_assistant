"""User preferences store backed by YAML."""

from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
import yaml


class UserPreferences(BaseModel):
  """User configuration preferences."""

  user_name: str = "Developer"
  preferred_language: str = "python"
  default_git_branch: str = "main"
  auto_summarize_tasks: bool = True
  custom_settings: Dict[str, Any] = Field(default_factory=dict)


class PreferencesManager:
  """Loads and saves user preferences to YAML file."""

  def __init__(self, file_path: Optional[Path] = None):
    self.file_path = (file_path or Path("config/preferences.yaml")).resolve()
    self.file_path.parent.mkdir(parents=True, exist_ok=True)
    self.preferences = self.load()

  def load(self) -> UserPreferences:
    if self.file_path.exists():
      try:
        with open(self.file_path, "r", encoding="utf-8") as f:
          data = yaml.safe_load(f) or {}
          return UserPreferences(**data)
      except Exception:
        pass
    return UserPreferences()

  def save(self, preferences: UserPreferences) -> None:
    self.preferences = preferences
    with open(self.file_path, "w", encoding="utf-8") as f:
      yaml.dump(self.preferences.model_dump(), f, default_flow_style=False)
