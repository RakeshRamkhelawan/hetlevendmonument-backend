"""
Contract Foundation Module

Implementeert de contract-gedreven architectuur voor workflow execution
per PRD v3.3 Fase 0.

Modules:
    - capability: Capability contracts en validatie
    - policy: Tenant policies en approval thresholds
    - enforcement: Runtime policy enforcement
    - trace: Execution tracing en observability
"""

import sys

_module = sys.modules[__name__]
if __name__ == "core.contracts":
    sys.modules.setdefault("src.core.contracts", _module)
elif __name__ == "src.core.contracts":
    sys.modules.setdefault("core.contracts", _module)

from typing import Any

# Capability Contract exports
from .capability import (
    AuditPolicy,
    CapabilityContract,
    CapabilityRegistry,
    CapabilityResolver,
    CapabilityValidationError,
    FallbackPolicy,
    RetryPolicy,
    SchemaMismatchError,
    UnknownCapabilityError,
    ValidationResult,
)

# Enforcement exports
from .enforcement import (
    EnforcementResult,
    PolicyEnforcer,
    can_execute_capability,
    require_approval_for,
)
from .legacy_trace import TraceCollector, TraceOutcome
from .legacy_trace import TraceStore as LegacyTraceStore

# Policy Contract exports
from .policy import (
    ApprovalRequirement,
    ApprovalThreshold,
    ComplianceProfile,
    PlanTier,
    PolicyCheckResult,
    TenantPolicy,
)
from .resolver import ResolutionResult

# Execution Trace exports
from .trace import (
    ExecutionSpan,
    ExecutionTrace,
    InMemoryTraceStore,
    SpanEvent,
    SpanStatus,
    SpanType,
    TraceBuilder,
    TraceContext,
    TraceStore,
    create_trace_context,
)

__all__ = [
    # Capability
    "CapabilityContract",
    "CapabilityRegistry",
    "CapabilityResolver",
    "ResolutionResult",
    "RetryPolicy",
    "FallbackPolicy",
    "AuditPolicy",
    "ValidationResult",
    "CapabilityValidationError",
    "UnknownCapabilityError",
    "SchemaMismatchError",
    # Policy
    "TenantPolicy",
    "PlanTier",
    "ComplianceProfile",
    "ApprovalThreshold",
    "ApprovalRequirement",
    "PolicyCheckResult",
    # Enforcement
    "PolicyEnforcer",
    "EnforcementResult",
    "can_execute_capability",
    "require_approval_for",
    # Trace
    "ExecutionTrace",
    "TraceOutcome",
    "ExecutionSpan",
    "SpanStatus",
    "SpanType",
    "SpanEvent",
    "TraceContext",
    "TraceBuilder",
    "TraceStore",
    "TraceCollector",
    "InMemoryTraceStore",
    "create_trace_context",
    "LegacyTraceStore",
]

__version__ = "0.3.0"
