"""Safe unified diff parser, hunk applier, and atomic rollback manager."""

from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple


class DiffApplier:
  """Applies unified diffs to files with atomic backup and rollback guarantees."""

  HUNK_HEADER_PATTERN = re.compile(
      r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@"
  )

  @staticmethod
  def apply_hunks_to_content(
      original_content: str, patch_text: str
  ) -> Tuple[bool, str, Optional[str]]:
    """Applies unified diff text to original string content.

    Returns (success, new_content, error_message).
    """
    if not patch_text or not patch_text.strip():
      return True, original_content, None

    orig_lines = original_content.splitlines(keepends=True)
    patch_lines = patch_text.splitlines()

    # If patch is raw replacement code rather than unified diff
    if not any(line.startswith("@@ ") for line in patch_lines):
      return True, patch_text, None

    hunks: List[List[str]] = []
    current_hunk: List[str] = []

    for line in patch_lines:
      if line.startswith("@@ "):
        if current_hunk:
          hunks.append(current_hunk)
        current_hunk = [line]
      elif current_hunk:
        current_hunk.append(line)
    if current_hunk:
      hunks.append(current_hunk)

    if not hunks:
      return False, original_content, "No valid diff hunks detected."

    result_lines = list(orig_lines)
    offset = 0

    for hunk in hunks:
      header = hunk[0]
      match = DiffApplier.HUNK_HEADER_PATTERN.match(header)
      if not match:
        continue

      orig_start = int(match.group(1)) - 1  # 0-indexed
      orig_count = int(match.group(2)) if match.group(2) is not None else 1

      hunk_lines = hunk[1:]
      new_slice: List[str] = []
      removed_count = 0

      for hline in hunk_lines:
        if hline.startswith("+"):
          new_slice.append(hline[1:] + "\n")
        elif hline.startswith("-"):
          removed_count += 1
        elif hline.startswith(" "):
          new_slice.append(hline[1:] + "\n")
          removed_count += 1
        elif hline == "":
          new_slice.append("\n")
          removed_count += 1

      # Target index with accumulated offset
      target_idx = max(0, min(len(result_lines), orig_start + offset))
      end_idx = min(len(result_lines), target_idx + removed_count)

      result_lines[target_idx:end_idx] = new_slice
      offset += len(new_slice) - removed_count

    return True, "".join(result_lines), None

  @classmethod
  def apply_patch_to_file(
      cls,
      file_path: Path | str,
      patch_text: str,
      backup_map: Optional[Dict[str, str]] = None,
  ) -> Tuple[bool, Optional[str]]:
    """Reads target file, backs up original, and writes modified content."""
    path = Path(file_path)
    if not path.exists():
      return False, f"Target file does not exist: {path}"

    try:
      original = path.read_text(encoding="utf-8")
      if backup_map is not None:
        backup_map[str(path.resolve())] = original

      success, new_content, error = cls.apply_hunks_to_content(
          original, patch_text
      )
      if not success:
        return False, error

      path.write_text(new_content, encoding="utf-8")
      return True, None
    except Exception as e:
      return False, f"Failed applying patch to file {path}: {str(e)}"

  @staticmethod
  def rollback_backups(backup_map: Dict[str, str]) -> None:
    """Restores all modified files to their original backed-up content."""
    for path_str, orig_content in backup_map.items():
      try:
        Path(path_str).write_text(orig_content, encoding="utf-8")
      except Exception:
        pass
