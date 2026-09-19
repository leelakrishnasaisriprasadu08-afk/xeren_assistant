"""Specialized autonomous subagents package."""

from .base import BaseSubagent, SubagentResult
from .coder import CoderSubagent
from .patcher import PatchSubagent
from .researcher import ResearchSubagent
from .reviewer import CodeReviewerSubagent
from .swarm import SwarmCoordinator, SwarmTurnRecord, SwarmWorkflowResult

__all__ = [
    "BaseSubagent",
    "SubagentResult",
    "ResearchSubagent",
    "CodeReviewerSubagent",
    "CoderSubagent",
    "PatchSubagent",
    "SwarmCoordinator",
    "SwarmTurnRecord",
    "SwarmWorkflowResult",
]
