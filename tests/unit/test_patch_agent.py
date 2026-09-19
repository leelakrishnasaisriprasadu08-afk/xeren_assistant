"""Unit tests for PatchSubagent execution."""

from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from agents.patcher import PatchSubagent
from models.provider import MockLLMProvider
from patching.patch_engine import PatchResult


@pytest.mark.asyncio
async def test_patch_subagent_execution(tmp_path: Path):
  test_file = tmp_path / "util.py"
  test_file.write_text("def ping(): return 'pong'\n", encoding="utf-8")

  mock_llm = MockLLMProvider()
  agent = PatchSubagent(llm_provider=mock_llm)

  # Mock PatchEngine generate_and_verify_patch
  mock_res = PatchResult(
      target_file="util.py",
      instruction="Update ping",
      patch_diff="+ return 'pong_v2'",
      tests_passed=True,
      test_output="1 passed",
      attempts=1,
      applied=True,
      success=True,
  )

  with patch.object(
      agent.patch_engine, "generate_and_verify_patch", new_callable=AsyncMock
  ) as mock_gen:
    mock_gen.return_value = mock_res

    res = await agent.run(
        goal="Update ping return value", context={"target_file": "util.py"}
    )

    assert res.success is True
    assert res.subagent_name == "patcher"
    assert "util.py" in res.findings
