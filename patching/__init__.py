"""Autonomous Test-Driven Patch Generation and Safe Diff Application package."""

from .diff_applier import DiffApplier
from .patch_engine import PatchEngine, PatchResult

__all__ = [
    "DiffApplier",
    "PatchEngine",
    "PatchResult",
]
