"""Unit tests for CodebaseIndexer and SQLite persistence."""

from pathlib import Path
import tempfile
import pytest
from codebase.indexer import CodebaseIndexer


def test_codebase_indexer_indexing_and_searching(tmp_path: Path):
  # Create sample files
  sub_dir = tmp_path / "service"
  sub_dir.mkdir(parents=True)

  file1 = sub_dir / "calculator.py"
  file1.write_text(
      """
class Calculator:
    \"\"\"Performs arithmetic calculations.\"\"\"
    def add(self, a: int, b: int) -> int:
        return a + b

    def subtract(self, a: int, b: int) -> int:
        return a - b
""",
      encoding="utf-8",
  )

  db_file = tmp_path / "test_indexer.sqlite"
  indexer = CodebaseIndexer(workspace_root=tmp_path, db_path=db_file)

  # Run workspace indexing
  stats = indexer.index_workspace(force=True)
  assert stats["files_scanned"] >= 1
  assert stats["total_symbols_indexed"] >= 3

  # Search symbols by name
  results = indexer.search_symbols(query="Calculator")
  assert len(results) >= 1
  assert results[0]["name"] == "Calculator"
  assert results[0]["type"] == "CLASS"

  # Search methods
  results_add = indexer.search_symbols(query="add")
  assert len(results_add) >= 1
  assert results_add[0]["name"] == "add"

  # Get file outline
  outline = indexer.get_file_outline("service/calculator.py")
  assert len(outline) >= 3
  names = [item["name"] for item in outline]
  assert "Calculator" in names
  assert "add" in names
