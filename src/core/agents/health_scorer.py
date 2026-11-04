"""Pure stateless health score computation for agent routing."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.agents.agent_router_agent import AgentManifest

_STATUS_MULTIPLIERS: dict[str, float] = {
    "HEALTHY": 1.0,
    "WARNING": 0.6,
    "CRITICAL": 0.1,
    "STALE": 0.2,
    "UNKNOWN": 0.5,
}
_MAX_LATENCY_MS: float = 5000.0
_W_SUCCESS: float = 0.4
_W_LATENCY: float = 0.3
_W_STATUS: float = 0.3


class HealthScorer:
    """Computes a composite health score in [0, 1] for an agent."""

    @staticmethod
    def score(
        success_rate: float,
        avg_latency_ms: float,
        health_status: str = "UNKNOWN",
    ) -> float:
        """Compute composite health score from three metrics.

        Args:
            success_rate: Fraction in [0, 1] of successful completions.
            avg_latency_ms: Average request latency in milliseconds.
            health_status: One of HEALTHY, WARNING, CRITICAL, STALE, UNKNOWN.
                Defaults to UNKNOWN.

        Returns:
            Composite score in [0, 1].
        """
        latency_norm = max(0.0, 1.0 - avg_latency_ms / _MAX_LATENCY_MS)
        status_mult = _STATUS_MULTIPLIERS.get(health_status.upper(), 0.5)
        raw = success_rate * _W_SUCCESS + latency_norm * _W_LATENCY + status_mult * _W_STATUS
        return max(0.0, min(1.0, raw))

    @staticmethod
    def score_manifest(manifest: AgentManifest) -> float:
        """Score an AgentManifest using its success_rate, avg_latency_ms, and health_status.

        health_status is read from manifest.health_status (set by AgentHealthMonitorAgent
        when health signals are available; defaults to "UNKNOWN" on new manifests).

        Args:
            manifest: AgentManifest with success_rate, avg_latency_ms, and health_status.

        Returns:
            Composite score in [0, 1].
        """
        return HealthScorer.score(
            success_rate=manifest.success_rate,
            avg_latency_ms=manifest.avg_latency_ms,
            health_status=manifest.health_status,
        )
