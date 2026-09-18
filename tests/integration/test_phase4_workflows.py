"""Integration tests for Phase 4 workflows: Long-term Semantic Memory, Subagent Delegation, and Shell/API routes."""

import pytest
from app.api import create_app
from config.settings import Settings
from core.assistant import XerenAssistant
from fastapi.testclient import TestClient
from memory.semantic import SemanticMemoryStore
from models.base import BaseLLMProvider, LLMResponse
from models.embeddings import LocalTFIDFEmbeddingProvider
from security.diff_engine import DiffEngine
from security.permission_gate import PermissionGate
from tools.registry import ToolRegistry
from tools.shell_tool import ShellTool
from tools.subagent_tool import SubagentTool


class MockPhase4LLM(BaseLLMProvider):
  async def generate(self, messages, system_instruction=None, temperature=0.0):
    user_prompt = messages[0].content
    if "Review Goal" in user_prompt:
      return LLMResponse(
          text="### Code Review Audit\n- **Security**: Passed\n- **Status**: PASSED",
          model_name="mock-reviewer",
      )
    return LLMResponse(
        text="### Phase 4 Analysis Complete\nSuccessfully processed task with long-term memory and subagent coordination.",
        model_name="mock-llm",
    )


@pytest.fixture
def phase4_assistant(tmp_path):
  """Instantiates a full XerenAssistant with Phase 4 memory, subagents, and test sandbox."""
  settings = Settings(
      workspace_root=tmp_path / "sandbox",
      db_path=tmp_path / "data" / "xeren_test.sqlite",
      traces_dir=tmp_path / "traces",
      preferences_path=tmp_path / "config" / "preferences.yaml",
  )
  settings.workspace_root.mkdir(parents=True, exist_ok=True)

  llm = MockPhase4LLM()
  gate = PermissionGate(
      workspace_root=settings.workspace_root,
      approval_callback=lambda req: True,
  )
  registry = ToolRegistry(permission_gate=gate)

  # Register tools
  registry.register_tool(ShellTool(workspace_root=settings.workspace_root))
  registry.register_tool(SubagentTool(llm_provider=llm, tool_registry=registry))

  embedding_provider = LocalTFIDFEmbeddingProvider(vector_dim=64)
  semantic_mem = SemanticMemoryStore(
      db_path=settings.db_path, embedding_provider=embedding_provider
  )

  assistant = XerenAssistant(
      settings=settings,
      llm_provider=llm,
      tool_registry=registry,
      semantic_memory=semantic_mem,
  )

  return assistant


@pytest.mark.asyncio
async def test_assistant_semantic_memory_indexing(phase4_assistant):
  """Test that assistant automatically indexes completed queries into semantic memory."""
  query = "How do we resolve SQLite database locks on Windows?"
  resp = await phase4_assistant.process_request(query)

  assert resp.success is True

  # Query semantic memory store
  results = await phase4_assistant.semantic_memory.search(
      query="Windows SQLite locks"
  )
  assert len(results) > 0
  assert query in results[0].memory.content


@pytest.mark.asyncio
async def test_assistant_subagent_delegation(phase4_assistant):
  """Test delegating code review to the CodeReviewerSubagent via the tool registry."""
  from core.dag import DAGAction, TaskGraph
  from security.policies import PermissionLevel, RiskLevel

  dag_act = DAGAction(
      action_id="act_review_01",
      tool_name="subagent",
      operation="delegate_code_review",
      parameters={
          "goal": "Review memory store implementation",
          "content": "class SemanticMemoryStore:\n    pass",
      },
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="Perform code review on new memory module",
  )

  graph = TaskGraph(actions=[dag_act])
  exec_res = await phase4_assistant.controller.execute_task_graph(graph)

  assert exec_res.success is True
  assert len(exec_res.step_records) == 1
  record = exec_res.step_records[0]
  assert record.tool_result.data["subagent_name"] == "code_reviewer"
  assert "PASSED" in record.tool_result.data["findings"]


def test_api_semantic_memory_endpoints(phase4_assistant):
  """Test the FastAPI /memory/semantic endpoints for querying and saving memories."""
  app = create_app(assistant=phase4_assistant)
  client = TestClient(app)

  # 1. Add memory via POST
  post_res = client.post(
      "/memory/semantic",
      json={
          "content": "Asyncio subprocesses require pipe buffering",
          "category": "architecture",
          "metadata": {"author": "engineer"},
      },
  )
  assert post_res.status_code == 200
  assert post_res.json()["status"] == "saved"

  # 2. Query memory via GET
  get_res = client.get("/memory/semantic?q=subprocess+buffering")
  assert get_res.status_code == 200
  data = get_res.json()
  assert "results" in data
  assert len(data["results"]) > 0
  assert "Asyncio subprocesses" in data["results"][0]["memory"]["content"]
