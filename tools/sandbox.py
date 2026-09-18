"""File modification sandbox providing atomic writes, snapshot backups, and rollback capabilities."""

import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Optional, Union


class FileSandbox:
  """Sandboxed file operations manager."""

  def __init__(self, workspace_root: Optional[Union[str, Path]] = None):
    root = Path(workspace_root) if workspace_root is not None else Path(".").resolve()
    self.workspace_root = root.resolve()
    self.backup_dir = self.workspace_root / ".xeren_backups"

  def _ensure_backup_dir(self) -> Path:
    self.backup_dir.mkdir(parents=True, exist_ok=True)
    return self.backup_dir

  def create_backup(self, target_path: Path) -> Optional[Path]:
    """Creates a timestamped snapshot of target_path before modification."""
    if not target_path.exists():
      return None

    bdir = self._ensure_backup_dir()
    rel_name = target_path.name
    timestamp = int(time.time() * 1000)
    backup_file = bdir / f"{rel_name}.{timestamp}.bak"

    shutil.copy2(target_path, backup_file)
    return backup_file

  def atomic_write(self, target_path: Path, content: str) -> Path:
    """Safely writes content to target_path using an atomic temp-file replace."""
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Create temporary file in the same directory to ensure same filesystem for atomic rename
    dir_name = target_path.parent
    prefix = f".tmp_{target_path.name}_"

    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=str(dir_name),
        prefix=prefix,
        delete=False,
        encoding="utf-8",
    ) as temp_file:
      temp_file.write(content)
      temp_path = Path(temp_file.name)

    # Atomically replace target file
    try:
      os.replace(temp_path, target_path)
    except Exception as e:
      if temp_path.exists():
        temp_path.unlink()
      raise RuntimeError(f"Atomic file write failed: {str(e)}")

    return target_path

  def rollback(self, target_path: Path, backup_path: Path) -> bool:
    """Restores target_path from a backup file."""
    if not backup_path.exists():
      return False

    try:
      shutil.copy2(backup_path, target_path)
      return True
    except Exception:
      return False
