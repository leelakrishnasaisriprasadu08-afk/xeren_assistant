"""Unit tests for multi-agent SwarmCoordinator collaboration workflow."""

import pytest
from agents.swarm import SwarmCoordinator
from models.base import BaseLLMProvider, LLMResponse


class MockSwarmLLM(BaseLLMProvider):
  async def generate(self, messages, system_instruction=None, temperature=0.0):
    user_prompt = messages[0].content
    if "Research Goal" in user_prompt:
      return LLMResponse(
          text="### Research Findings\n- Pattern: Use connection pooling with timeout bounds.\n- Citation: PEP 249",
          model_name="mock-researcher",
      )
    elif "Audit code" in user_prompt:
      return LLMResponse(
          text="### Audit Review\n- Status: PASSED\n- Security: No SQL injection or thread race condition detected.",
          model_name="mock-reviewer",
      )
    else:
      return LLMResponse(
          text="```python\nclass ConnectionPool:\n    def __init__(self):\n        pass\n```",
          model_name="mock-coder",
      )


@pytest.mark.asyncio
async def test_swarm_collaborative_workflow():
  """Test that SwarmCoordinator coordinates turns across Researcher, Coder, and Reviewer."""
  llm = MockSwarmLLM()
  coordinator = SwarmCoordinator(llm_provider=llm)

  result = await coordinator.collaborate(
      prompt="Build an async SQLite connection pooler"
  )

  assert result.consensus_reached is True
  assert len(result.turns) >= 3

  # Turn 1: researcher
  assert result.turns[0].agent_name == "researcher"
  assert "PEP 249" in result.turns[0].output

  # Turn 2: coder
  assert result.turns[1].agent_name == "coder"
  assert "class ConnectionPool" in result.turns[1].output

  # Turn 3: reviewer
  assert result.turns[2].agent_name == "code_reviewer"
  assert "PASSED" in result.turns[2].output

  # Final artifact
  assert "class ConnectionPool" in result.final_artifact
