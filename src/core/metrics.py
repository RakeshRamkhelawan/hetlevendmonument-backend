# core/metrics.py
"""
Legacy metrics module - re-exports from observability.metrics to avoid duplication.
This file exists for backward compatibility.
"""

# Import from the singleton-protected observability module

# Create tool-specific metrics (these don't conflict with HTTP metrics)


from src.core.observability.metrics import _get_or_create_counter, _get_or_create_histogram

TOOL_EXECUTION_COUNT = _get_or_create_counter(
    "tool_execution_total", "Total Tool Executions", ["tool_name", "status"]
)

TOOL_AUDIT_WRITE_FAILURES = _get_or_create_counter(
    "tool_audit_write_failures_total",
    "Tool audit-log writes that failed (the tool action itself is unaffected)",
    ["error_type"],
)

TOOL_EXECUTION_LATENCY = _get_or_create_histogram(
    "tool_execution_duration_seconds", "Tool Execution Latency", ["tool_name"]
)
