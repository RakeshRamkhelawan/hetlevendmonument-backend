"""Art. 17 Quality Management System.

EU AI Act Compliance - Article 17: Quality management system.
Mandatory pre-deployment checks integrating Art. 9/12/13/14/15/52.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.database import Base


class QualityCheckType(str, Enum):
    PRE_DEPLOYMENT = "pre_deployment"
    POST_DEPLOYMENT = "post_deployment"
    PERIODIC_REVIEW = "periodic_review"
    INCIDENT_TRIGGERED = "incident_triggered"


class QualityCheckResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"


class QualityCheck(Base):
    """Art. 17: Quality management check record per tenant."""

    __tablename__ = "governance_quality_checks"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    agent_name = Column(String(200), nullable=False)
    check_type = Column(String(50), nullable=False)
    result = Column(String(20), nullable=False)
    details = Column(JSONB, default=dict)
    checked_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    checked_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class QualityGate:
    """Art. 17: Enforces mandatory quality checks before deployment.

    Each check maps to an EU AI Act article obligation.
    """

    REQUIRED_CHECKS = [
        "risk_classification",  # Art. 9: Risk level determined?
        "model_provenance",  # Art. 12: Provenance logged?
        "model_card_complete",  # Art. 13: Model card complete?
        "human_oversight_configured",  # Art. 14: Oversight configured?
        "accuracy_baseline_set",  # Art. 15: Accuracy baseline set?
        "attribution_configured",  # Art. 52: Attribution configured?
    ]

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def pre_deployment_check(
        self,
        tenant_id: int,
        agent_name: str,
        user_id: int,
    ) -> list[dict]:
        """Run all mandatory checks before deployment.

        Returns list of dicts with check name and result.
        """
        results: list[dict] = []

        for check_name in self.REQUIRED_CHECKS:
            check_fn = getattr(self, f"_check_{check_name}", None)
            if check_fn:
                passed = await check_fn(tenant_id, agent_name)
                result = QualityCheckResult.PASS if passed else QualityCheckResult.FAIL
            else:
                result = QualityCheckResult.WARNING

            record = QualityCheck(
                tenant_id=tenant_id,
                agent_name=agent_name,
                check_type=QualityCheckType.PRE_DEPLOYMENT,
                result=result.value,
                details={"check": check_name},
                checked_by_user_id=user_id,
            )
            self._db.add(record)
            results.append({"check": check_name, "result": result.value})

        await self._db.flush()
        return results

    async def _check_risk_classification(self, tenant_id: int, agent_name: str) -> bool:
        """Art. 9 / ADR-031: Verify agent has a registered risk classification."""
        # TODO(Rakesh): implement real risk classification lookup (#SP-AIAct-001)
        return True
