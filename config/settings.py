"""Application settings and environment configuration loader."""

from functools import lru_cache
from pathlib import Path
from typing import Optional
import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
  """Application configuration settings."""

  model_config = SettingsConfigDict(
      env_file=".env",
      env_file_encoding="utf-8",
      extra="ignore",
      env_prefix="XEREN_",
  )

  # App metadata
  app_name: str = "Xeren Assistant"
  version: str = "0.1.0"
  environment: str = "development"

  # Workspace & Paths
  workspace_root: Path = Field(default_factory=lambda: Path(".").resolve())
  db_path: Path = Path("data/xeren.sqlite")
  traces_dir: Path = Path("traces")
  preferences_path: Path = Path("config/preferences.yaml")

  # Execution safety & limits
  max_steps_per_task: int = 10
  max_retries_per_step: int = 2
  task_timeout_seconds: float = 60.0
  tool_timeout_seconds: float = 10.0

  # Security policies
  strict_path_containment: bool = True
  block_deletions: bool = True
  redact_secrets_in_logs: bool = True

  # API Keys (Loaded from environment, never logged or serialized)
  gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
  github_token: Optional[str] = Field(default=None, alias="GITHUB_TOKEN")

  @classmethod
  def load_with_yaml(
      cls, yaml_path: Optional[Path] = None, **kwargs
  ) -> "Settings":
    """Loads configuration prioritizing ENV, then YAML defaults."""
    data = {}
    target_yaml = yaml_path or Path("config/settings.yaml")
    if target_yaml.exists():
      try:
        with open(target_yaml, "r", encoding="utf-8") as f:
          raw_yaml = yaml.safe_load(f) or {}

        # Flatten nested sections
        if "app" in raw_yaml:
          data["app_name"] = raw_yaml["app"].get("name", "Xeren Assistant")
          data["version"] = raw_yaml["app"].get("version", "0.1.0")
          data["environment"] = raw_yaml["app"].get(
              "environment", "development"
          )
        if "execution" in raw_yaml:
          data["max_steps_per_task"] = raw_yaml["execution"].get(
              "max_steps_per_task", 10
          )
          data["max_retries_per_step"] = raw_yaml["execution"].get(
              "max_retries_per_step", 2
          )
          data["task_timeout_seconds"] = raw_yaml["execution"].get(
              "task_timeout_seconds", 60.0
          )
          data["tool_timeout_seconds"] = raw_yaml["execution"].get(
              "tool_timeout_seconds", 10.0
          )
        if "security" in raw_yaml:
          data["strict_path_containment"] = raw_yaml["security"].get(
              "strict_path_containment", True
          )
          data["block_deletions"] = raw_yaml["security"].get(
              "block_deletions", True
          )
          data["redact_secrets_in_logs"] = raw_yaml["security"].get(
              "redact_secrets_in_logs", True
          )
        if "storage" in raw_yaml:
          if "db_path" in raw_yaml["storage"]:
            data["db_path"] = Path(raw_yaml["storage"]["db_path"])
          if "traces_dir" in raw_yaml["storage"]:
            data["traces_dir"] = Path(raw_yaml["storage"]["traces_dir"])
          if "preferences_path" in raw_yaml["storage"]:
            data["preferences_path"] = Path(
                raw_yaml["storage"]["preferences_path"]
            )
      except Exception:
        pass  # Fallback to class defaults

    data.update(kwargs)
    return cls(**data)


@lru_cache()
def get_settings() -> Settings:
  """Returns cached singleton application settings."""
  settings = Settings.load_with_yaml()
  # Ensure storage directories exist
  settings.db_path.parent.mkdir(parents=True, exist_ok=True)
  settings.traces_dir.mkdir(parents=True, exist_ok=True)
  settings.workspace_root = settings.workspace_root.resolve()
  return settings
