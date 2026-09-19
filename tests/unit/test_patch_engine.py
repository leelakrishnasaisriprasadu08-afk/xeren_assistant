"""Unit tests for autonomous PatchEngine and test-driven self-healing."""

from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from models.provider import MockLLMProvider
from patching.patch_engine import PatchEngine, PatchResult


@pytest.mark.asyncio
async def test_patch_engine_generate_and_verify_success(tmp_path: Path):
  # Setup sample source and passing test in temporary workspace
  src_file = tmp_path / "math_lib.py"
  src_file.write_text(
      """
def multiply(a: int, b: int) -> int:
    return a + b  # Bug: adding instead of multiplying
""",
      encoding="utf-8",
  )

  fixed_code = """```python
def multiply(a: int, b: int) -> int:
    return a * b
```"""

  mock_llm = MockLLMProvider(canned_response=fixed_code)
  engine = PatchEngine(workspace_root=tmp_path, llm_provider=mock_llm)

  # Mock test execution as passing
  with patch.object(
      engine, "_run_tests", new_callable=AsyncMock
  ) as mock_test_run:
    mock_test_run.return_value = (True, "1 passed in 0.05s")

    result: PatchResult = await engine.generate_and_verify_patch(
        target_file="math_lib.py",
        instruction="Fix bug in multiply to multiply instead of add",
        max_retries=1,
    )

    assert result.success is True
    assert result.tests_passed is True
    assert result.applied is True
    assert "return a * b" in src_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_patch_engine_self_healing_retry(tmp_path: Path):
  src_file = tmp_path / "validator.py"
  src_file.write_text("def is_positive(n): return False\n", encoding="utf-8")

  # Mock LLM provides bad response first, then fixed code
  mock_llm = MockLLMProvider(
      canned_response="```python\ndef is_positive(n): return n > 0\n```"
  )
  engine = PatchEngine(workspace_root=tmp_path, llm_provider=mock_llm)

  # First test fails, second test passes
  with patch.object(
      engine, "_run_tests", new_callable=AsyncMock
  ) as mock_test_run:
    mock_test_run.side_effect = [
        (False, "AssertionError: Expected True, got False"),
        (True, "1 passed in 0.02s"),
    ]

    result: PatchResult = await engine.generate_and_verify_patch(
        target_file="validator.py",
        instruction="Fix is_positive function",
        max_retries=2,
    )

    assert result.success is True
    assert result.attempts == 2
    assert result.tests_passed is True
