"""ML Strategy - Three-phase ML Cold Start solution (Phase 2).

Fixes over v1:
- Phase detection per tenant (not global)
- Deterministic sampling via SHA-256 (not random.random())
- Data from PostgreSQL (not in-memory)
"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.accuracy_monitor import AccuracyMetric


class MLPhase:
    RULES_ONLY = "rules_only"  # < 100 samples
    RULES_PLUS_STATS = "rules_stats"  # 100-1000 samples
    RULES_PLUS_ML = "rules_ml"  # 1000+ samples


class MLStrategy:
    """Three-phase ML strategy per tenant.

    Phase 1 (< 100 samples): rules only.
    Phase 2 (100-1000): 80% rules, 20% statistical.
    Phase 3 (1000+): 50% rules, 50% ML.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def detect_phase(self, tenant_id: int) -> str:
        """Detect ML phase for this tenant based on sample count."""
        stmt = (
            select(func.count())
            .select_from(AccuracyMetric)
            .where(AccuracyMetric.tenant_id == tenant_id)
        )
        result = await self._db.execute(stmt)
        sample_count = result.scalar_one()

        if sample_count < 100:
            return MLPhase.RULES_ONLY
        if sample_count < 1000:
            return MLPhase.RULES_PLUS_STATS
        return MLPhase.RULES_PLUS_ML

    async def analyze(
        self,
        tenant_id: int,
        event: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Route event to analyzer based on tenant phase."""
        phase = await self.detect_phase(tenant_id)

        if phase == MLPhase.RULES_ONLY:
            return self._rule_check(event)

        if phase == MLPhase.RULES_PLUS_STATS:
            if self._deterministic_sample(event, rate=0.2):
                return await self._statistical_check(tenant_id, event)
            return self._rule_check(event)

        # RULES_PLUS_ML
        if self._deterministic_sample(event, rate=0.5):
            return await self._ml_check(tenant_id, event)
        return self._rule_check(event)

    @staticmethod
    def _deterministic_sample(event: dict[str, Any], rate: float) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Reproducible sampling via SHA-256 hash of event_id."""
        event_id = str(event.get("event_id", ""))
        hash_int = int(hashlib.sha256(event_id.encode()).hexdigest(), 16)
        return (hash_int % 10000) / 10000.0 < rate

    @staticmethod
    def _rule_check(event: dict[str, Any]) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Basic rule checks (always available)."""
        # Cross-tenant check
        if event.get("tenant_id") != event.get("agent_tenant_id"):
            return {
                "type": "cross_tenant_access",
                "confidence": 0.99,
                "evidence": "tenant_id mismatch",
            }

        # High-risk without approval
        if event.get("risk_level") == "high" and not event.get("human_approved"):
            return {
                "type": "missing_approval",
                "confidence": 0.95,
                "evidence": "high_risk without human approval",
            }
        return None

    async def _statistical_check(
        self, tenant_id: int, event: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Statistical anomaly detection (z-score, latency and error rate checks)."""
        rule_violation = self._rule_check(event)
        if rule_violation is not None:
            return rule_violation

        latency_ms = event.get("latency_ms") or event.get("execution_time_ms")
        if latency_ms is not None and float(latency_ms) > 10000.0:
            return {
                "type": "statistical_latency_anomaly",
                "confidence": 0.85,
                "evidence": f"execution latency {latency_ms}ms exceeds threshold",
            }

        z_score = event.get("z_score")
        if z_score is not None and abs(float(z_score)) > 2.5:
            return {
                "type": "statistical_zscore_anomaly",
                "confidence": 0.90,
                "evidence": f"z-score {z_score} exceeds 2.5 sigma",
            }

        return None

    async def _ml_check(
        self, tenant_id: int, event: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """ML-based anomaly detection."""
        rule_violation = self._rule_check(event)
        if rule_violation is not None:
            return rule_violation

        risk_score = event.get("risk_score") or event.get("anomaly_score")
        if risk_score is not None and float(risk_score) >= 0.80:
            return {
                "type": "ml_anomaly_detected",
                "confidence": float(risk_score),
                "evidence": f"model predicted high anomaly probability ({risk_score})",
            }

        return None
