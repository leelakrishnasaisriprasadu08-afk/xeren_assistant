"""Integration tests for the full end-to-end execution pipeline."""

import pytest
from core.assistant import XerenAssistant
from models.provider import MockLLMProvider
from tools.registry import get_default_registry


@pytest.mark.asyncio
async def test_full_pipeline_filesystem_query(test_settings):
  registry = get_default_registry(test_settings)
  mock_llm = MockLLMProvider()

  assistant = XerenAssistant(
      settings=test_settings, tool_registry=registry, llm_provider=mock_llm
  )

  # Run file read request
  resp = await assistant.process_request("read file README.md")

  assert resp.success is True
  assert "Read File `README.md`" in resp.response_text
  assert resp.trace_id != ""
  assert resp.duration_ms > 0

  # Verify trace was written to disk
  trace_file = test_settings.traces_dir / "traces.jsonl"
  assert trace_file.exists()
  content = trace_file.read_text(encoding="utf-8")
  assert resp.trace_id in content


@pytest.mark.asyncio
async def test_full_pipeline_task_creation(test_settings):
  registry = get_default_registry(test_settings)
  assistant = XerenAssistant(settings=test_settings, tool_registry=registry)

  resp = await assistant.process_request("create task test end to end pipeline")

  assert resp.success is True
  assert "Created Task #1" in resp.response_text
