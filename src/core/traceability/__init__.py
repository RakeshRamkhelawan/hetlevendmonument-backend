"""
Fase 4: Traceability Matrix PRD -> Code -> Tests

Provides complete traceability from requirements to implementation.
"""

from typing import Any

from .matrix import (
    CoverageStatus,
    Implementation,
    Requirement,
    RequirementType,
    TestEvidence,
    TraceabilityMatrix,
)
from .validator import GateStatus, ReleaseGate, TraceabilityValidator, ValidationReport

__all__ = [
    "TraceabilityMatrix",
    "Requirement",
    "RequirementType",
    "Implementation",
    "TestEvidence",
    "CoverageStatus",
    "TraceabilityValidator",
    "ValidationReport",
    "ReleaseGate",
    "GateStatus",
]
