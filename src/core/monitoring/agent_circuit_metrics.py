"""Prometheus metrics for AgentCircuitBreaker."""

from __future__ import annotations
from prometheus_client import Counter, Gauge

AGENT_CIRCUIT_STATE = Gauge(
    "agent_circuit_state",
    "Circuit breaker state: 0=closed, 1=open, 2=half_open",
    ["tenant_id", "agent_id"],
)

AGENT_CIRCUIT_FAILURES_TOTAL = Counter(
    "agent_circuit_failures_total",
    "Total failures recorded by circuit breaker",
    ["tenant_id", "agent_id"],
)

AGENT_CIRCUIT_SUCCESSES_TOTAL = Counter(
    "agent_circuit_successes_total",
    "Total successes recorded by circuit breaker",
    ["tenant_id", "agent_id"],
)

AGENT_CIRCUIT_OPENS_TOTAL = Counter(
    "agent_circuit_opens_total",
    "Total times circuit opened",
    ["tenant_id", "agent_id"],
)


def _state_to_float(state: object) -> float:
    from src.core.als.infrastructure.agent_circuit_breaker import CircuitState

    state_map: dict[CircuitState, float] = {
        CircuitState.CLOSED: 0.0,
        CircuitState.OPEN: 1.0,
        CircuitState.HALF_OPEN: 2.0,
    }
    if isinstance(state, CircuitState):
        return state_map[state]
    return 0.0
