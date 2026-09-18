"""Multi-Agent Swarm Collaboration and Consensus Coordinator."""

import time
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field
from models.base import BaseLLMProvider
from tools.registry import ToolRegistry
from .coder import CoderSubagent
from .researcher import ResearchSubagent
from .reviewer import CodeReviewerSubagent


class SwarmTurnRecord(BaseModel):
  """Record of an individual turn in a multi-agent swarm collaboration."""

  turn_index: int
  agent_name: str
  role: str
  goal: str
  output: str
  duration_ms: float = 0.0
  timestamp: float = Field(default_factory=time.time)


class SwarmWorkflowResult(BaseModel):
  """Comprehensive outcome of a multi-agent collaborative swarm execution."""

  workflow_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
  prompt: str
  consensus_reached: bool = True
  iterations: int = 1
  turns: List[SwarmTurnRecord] = Field(default_factory=list)
  final_artifact: str = ""
  total_duration_ms: float = 0.0
  error: Optional[str] = None


class SwarmCoordinator:
  """Coordinates autonomous multi-agent handoffs and iterative consensus loops."""

  def __init__(
      self,
      llm_provider: BaseLLMProvider,
      tool_registry: Optional[ToolRegistry] = None,
  ):
    self.llm_provider = llm_provider
    self.tool_registry = tool_registry
    self.researcher = ResearchSubagent(
        llm_provider=llm_provider, tool_registry=tool_registry
    )
    self.coder = CoderSubagent(
        llm_provider=llm_provider, tool_registry=tool_registry
    )
    self.reviewer = CodeReviewerSubagent(
        llm_provider=llm_provider, tool_registry=tool_registry
    )

  async def collaborate(
      self, prompt: str, max_iterations: int = 2
  ) -> SwarmWorkflowResult:
    """Executes a multi-agent collaborative cycle: Research -> Implementation -> Audit -> Refinement."""
    start_total_time = time.perf_counter()
    turns: List[SwarmTurnRecord] = []
    turn_idx = 1

    # Turn 1: Research Agent
    t1_start = time.perf_counter()
    res_research = await self.researcher.run(
        goal=f"Research best practices and architecture for: {prompt}"
    )
    t1_ms = (time.perf_counter() - t1_start) * 1000
    turns.append(
        SwarmTurnRecord(
            turn_index=turn_idx,
            agent_name=self.researcher.name,
            role=self.researcher.role_description,
            goal="Explore domain architecture and best practices",
            output=res_research.findings or "No research dossier available.",
            duration_ms=t1_ms,
        )
    )
    turn_idx += 1

    # Turn 2: Coder Agent (Draft 1)
    t2_start = time.perf_counter()
    res_code = await self.coder.run(
        goal=prompt,
        context={"research_dossier": res_research.findings},
    )
    t2_ms = (time.perf_counter() - t2_start) * 1000
    current_code = res_code.findings
    turns.append(
        SwarmTurnRecord(
            turn_index=turn_idx,
            agent_name=self.coder.name,
            role=self.coder.role_description,
            goal="Synthesize initial code implementation",
            output=current_code,
            duration_ms=t2_ms,
        )
    )
    turn_idx += 1

    # Turn 3: Reviewer Agent (Audit)
    t3_start = time.perf_counter()
    res_review = await self.reviewer.run(
        goal=f"Audit code implementation for: {prompt}",
        context={"content": current_code},
    )
    t3_ms = (time.perf_counter() - t3_start) * 1000
    turns.append(
        SwarmTurnRecord(
            turn_index=turn_idx,
            agent_name=self.reviewer.name,
            role=self.reviewer.role_description,
            goal="Audit implementation against security and quality standards",
            output=res_review.findings,
            duration_ms=t3_ms,
        )
    )
    turn_idx += 1

    # Check if refinement is required
    needs_refinement = (
        "CRITICAL" in res_review.findings
        or "HIGH" in res_review.findings
        or "recommend" in res_review.findings.lower()
    )

    if needs_refinement and max_iterations > 1:
      # Turn 4: Coder Refinement
      t4_start = time.perf_counter()
      res_refined = await self.coder.run(
          goal=prompt,
          context={
              "research_dossier": res_research.findings,
              "existing_code": current_code,
              "review_feedback": res_review.findings,
          },
      )
      t4_ms = (time.perf_counter() - t4_start) * 1000
      current_code = res_refined.findings
      turns.append(
          SwarmTurnRecord(
              turn_index=turn_idx,
              agent_name=self.coder.name,
              role=self.coder.role_description,
              goal="Refine implementation according to reviewer audit findings",
              output=current_code,
              duration_ms=t4_ms,
          )
      )

    total_ms = (time.perf_counter() - start_total_time) * 1000
    return SwarmWorkflowResult(
        prompt=prompt,
        consensus_reached=True,
        iterations=len(turns),
        turns=turns,
        final_artifact=current_code,
        total_duration_ms=total_ms,
    )
