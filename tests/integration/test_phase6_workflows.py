"""Integration tests for Phase 6 Codebase Indexer and Patch Studio REST APIs."""

from pathlib import Path
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
import pytest
from app.api import create_app
from core.assistant import XerenAssistant
from patching.patch_engine import PatchResult


@pytest.fixture
def client(tmp_path: Path):
  from config.settings import Settings

  settings = Settings(workspace_root=tmp_path, db_path=tmp_path / "test.sqlite")
  assistant = XerenAssistant(settings=settings)
  app = create_app(assistant)
  return TestClient(app)


def test_api_codebase_indexing_and_symbol_queries(
    client: TestClient, tmp_path: Path
):
  # Create a test file in the workspace
  sample_py = tmp_path / "core_mod.py"
  sample_py.write_text(
      """
class CoreEngine:
    \"\"\"Main engine.\"\"\"
    def start(self) -> bool:
        return True
""",
      encoding="utf-8",
  )

  # Trigger indexing via API
  res_idx = client.post("/codebase/index", json={"force": True})
  assert res_idx.status_code == 200
  idx_data = res_idx.json()
  assert idx_data["files_scanned"] >= 1

  # Search symbols
  res_sym = client.get("/codebase/symbols?query=CoreEngine")
  assert res_sym.status_code == 200
  sym_data = res_sym.json()
  assert len(sym_data["symbols"]) >= 1
  assert sym_data["symbols"][0]["name"] == "CoreEngine"

  # Get file outline
  res_out = client.get("/codebase/outline?file_path=core_mod.py")
  assert res_out.status_code == 200
  out_data = res_out.json()
  assert len(out_data["outline"]) >= 2

  # Get call graph
  res_cg = client.get("/codebase/call-graph?symbol_name=start")
  assert res_cg.status_code == 200


def test_api_patch_generation_and_application(client: TestClient):
  # Mock generate_and_verify_patch
  mock_patch_res = PatchResult(
      target_file="test_target.py",
      instruction="Fix return code",
      patch_diff="+ return 200",
      tests_passed=True,
      test_output="1 passed",
      attempts=1,
      applied=True,
      success=True,
  )

  with patch(
      "patching.patch_engine.PatchEngine.generate_and_verify_patch",
      new_callable=AsyncMock,
  ) as mock_gen:
    mock_gen.return_value = mock_patch_res

    res = client.post(
        "/patch/generate",
        json={
            "target_file": "test_target.py",
            "instruction": "Fix return code",
            "dry_run": False,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["tests_passed"] is True
