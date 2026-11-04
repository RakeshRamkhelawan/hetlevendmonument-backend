"""
Prometheus metrics for sandbox code execution.

Registered at module-import time (prometheus_client global registry).
Import this module in TenantSandboxOrchestrator and ProductionSandboxManager
to enable instrumentation.
"""

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Execution counters
# ---------------------------------------------------------------------------

SANDBOX_EXECUTIONS_TOTAL = Counter(
    "sandbox_executions_total",
    "Total sandbox code executions",
    ["tenant_id", "language", "success"],
)

SANDBOX_SECURITY_VIOLATIONS = Counter(
    "sandbox_security_violations_total",
    "Security violations caught by CodeSecurityScanner",
    ["tenant_id", "threat_level"],
)

# ---------------------------------------------------------------------------
# Duration histogram
# ---------------------------------------------------------------------------

SANDBOX_EXECUTION_DURATION = Histogram(
    "sandbox_execution_duration_seconds",
    "Sandbox code execution wall-clock duration",
    ["tenant_id", "language"],
    buckets=[0.1, 0.5, 1.0, 5.0, 15.0, 30.0, 60.0],
)

# ---------------------------------------------------------------------------
# Live state gauge
# ---------------------------------------------------------------------------

ACTIVE_SANDBOXES = Gauge(
    "sandbox_active_count",
    "Currently active sandbox containers per tenant",
    ["tenant_id"],
)
