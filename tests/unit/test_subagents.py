"""Unit tests for ResearchSubagent, CodeReviewerSubagent, and SubagentTool."""

import pytest
from agents.researcher import ResearchSubagent
from agents.reviewer import CodeReviewerSubagent
from models.base import BaseLLMProvider, LLMResponse
from security.policies import PermissionLevel, RiskLevel
from tools.base import Action
from tools.registry import ToolRegistry
from tools.subagent_tool import SubagentTool


class MockSubagentLLM(BaseLLMProvider):
  async def generate(self, messages, system_instruction=None, temperature=0.0):
    user_prompt = messages[0].content
    if "Review Goal" in user_prompt:
      return LLMResponse(
          text="### Code Review Audit Report\n- **Severity**: LOW\n- **Security**: No path traversal or SQL injection found.\n- **Status**: PASSED",
          model_name="mock-reviewer",
      )
    else:
      return LLMResponse(
          text="### Technical Research Dossier\n- **Summary**: FastAPI uses AnyIO and Starlette for high performance asynchronous execution.\n- **Citations**: [FastAPI Docs](https://fastapi.tiangolo.com)",
          model_name="mock-researcher",
      )


@pytest.mark.asyncio
async def test_research_subagent_run():
  """Test running the ResearchSubagent independently."""
  llm = MockSubagentLLM()
  researcher = ResearchSubagent(llm_provider=llm)

  res = await researcher.run(goal="Research modern Python async frameworks")
  assert res.success is True
  assert res.subagent_name == "researcher"
  assert "FastAPI" in res.findings


@pytest.mark.asyncio
async def test_code_reviewer_subagent_run():
  """Test running the CodeReviewerSubagent on a code snippet."""
  llm = MockSubagentLLM()
  reviewer = CodeReviewerSubagent(llm_provider=llm)

  code_snippet = "def sanitize_path(p):\n    return Path(p).resolve()"
  res = await reviewer.run(
      goal="Check path sanitization function",
      context={"content": code_snippet, "file_path": "security/path.py"},
  )

  assert res.success is True
  assert res.subagent_name == "code_reviewer"
  assert "Code Review Audit" in res.findings


@pytest.mark.asyncio
async def test_subagent_tool_delegation():
  """Test delegating tasks via SubagentTool through the Action schema."""
  llm = MockSubagentLLM()
  tool = SubagentTool(llm_provider=llm)

  # 1. Test delegate_research
  act_res = Action(
      action_id="sub_01",
      tool_name="subagent",
      operation="delegate_research",
      parameters={"goal": "Investigate SQLite write locks"},
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="Perform research",
  )
  res1 = await tool.execute(act_res)
  assert res1.success is True
  assert "FastAPI" in res1.data.get("findings", "")

  # 2. Test delegate_code_review
  act_rev = Action(
      action_id="sub_02",
      tool_name="subagent",
      operation="delegate_code_review",
      parameters={
          "goal": "Audit diff",
          "diff": "+import os\n-import os",
      },
      required_permission=PermissionLevel.ALLOWED,
      risk_level=RiskLevel.LOW,
      reason="Review diff",
  )
  res2 = await tool.execute(act_rev)
  assert res2.success is True
  assert "PASSED" in res2.data.get("findings", "")
