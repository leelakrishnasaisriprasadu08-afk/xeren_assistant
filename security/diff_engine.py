"""Visual Diff generation and code change summary engine."""

import difflib
from typing import Any, Dict


class DiffEngine:
  """Generates unified diffs and computes impact summaries for proposed file changes."""

  @staticmethod
  def generate_unified_diff(
      old_content: str,
      new_content: str,
      file_path: str = "file",
  ) -> str:
    """Generates a git-style unified diff string between old and new text."""
    old_lines = old_content.splitlines(keepends=True) if old_content else []
    new_lines = new_content.splitlines(keepends=True) if new_content else []

    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="\n",
        )
    )

    if not diff_lines:
      return "(No changes detected)"

    return "".join(diff_lines)

  @staticmethod
  def summarize_change(
      old_content: str,
      new_content: str,
  ) -> Dict[str, Any]:
    """Calculates quantitative metrics about line additions, deletions, and byte deltas."""
    old_lines = old_content.splitlines() if old_content else []
    new_lines = new_content.splitlines() if new_content else []

    diff = list(
        difflib.ndiff(old_lines, new_lines)
    )

    added_count = sum(1 for line in diff if line.startswith("+ "))
    removed_count = sum(1 for line in diff if line.startswith("- "))
    unchanged_count = sum(1 for line in diff if line.startswith("  "))

    old_bytes = len(old_content.encode("utf-8")) if old_content else 0
    new_bytes = len(new_content.encode("utf-8")) if new_content else 0

    return {
        "lines_added": added_count,
        "lines_removed": removed_count,
        "lines_unchanged": unchanged_count,
        "old_size_bytes": old_bytes,
        "new_size_bytes": new_bytes,
        "delta_bytes": new_bytes - old_bytes,
        "is_new_file": len(old_lines) == 0 and len(new_lines) > 0,
    }
