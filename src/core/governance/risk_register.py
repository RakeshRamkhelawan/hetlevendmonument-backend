"""Art. 9 Risk Management System - Risk Register.

EU AI Act Compliance - Article 9: Risk Management System
Persistent risk register for AI agents per tenant.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from src.core.database.database import Base


class RiskLikelihood(str, Enum):
    RARE = "rare"
    UNLIKELY = "unlikely"
    POSSIBLE = "possible"
    LIKELY = "likely"
    ALMOST_CERTAIN = "almost_certain"


class RiskImpact(str, Enum):
    NEGLIGIBLE = "negligible"
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    CATASTROPHIC = "catastrophic"


RISK_MATRIX: dict[tuple[RiskLikelihood, RiskImpact], str] = {
    # Unacceptable
    (RiskLikelihood.ALMOST_CERTAIN, RiskImpact.CATASTROPHIC): "unacceptable",
    (RiskLikelihood.ALMOST_CERTAIN, RiskImpact.MAJOR): "unacceptable",
    (RiskLikelihood.LIKELY, RiskImpact.CATASTROPHIC): "unacceptable",
    # High
    (RiskLikelihood.LIKELY, RiskImpact.MAJOR): "high",
    (RiskLikelihood.POSSIBLE, RiskImpact.CATASTROPHIC): "high",
    (RiskLikelihood.POSSIBLE, RiskImpact.MAJOR): "high",
    (RiskLikelihood.ALMOST_CERTAIN, RiskImpact.MODERATE): "high",
    # Medium
    (RiskLikelihood.POSSIBLE, RiskImpact.MODERATE): "medium",
    (RiskLikelihood.LIKELY, RiskImpact.MODERATE): "medium",
    (RiskLikelihood.UNLIKELY, RiskImpact.MAJOR): "medium",
    (RiskLikelihood.UNLIKELY, RiskImpact.CATASTROPHIC): "medium",
    # Low
    (RiskLikelihood.RARE, RiskImpact.NEGLIGIBLE): "low",
    (RiskLikelihood.RARE, RiskImpact.MINOR): "low",
    (RiskLikelihood.RARE, RiskImpact.MODERATE): "low",
    (RiskLikelihood.UNLIKELY, RiskImpact.NEGLIGIBLE): "low",
    (RiskLikelihood.UNLIKELY, RiskImpact.MINOR): "low",
    (RiskLikelihood.UNLIKELY, RiskImpact.MODERATE): "low",
    (RiskLikelihood.POSSIBLE, RiskImpact.NEGLIGIBLE): "low",
    (RiskLikelihood.POSSIBLE, RiskImpact.MINOR): "low",
    (RiskLikelihood.LIKELY, RiskImpact.NEGLIGIBLE): "low",
    (RiskLikelihood.LIKELY, RiskImpact.MINOR): "low",
    (RiskLikelihood.ALMOST_CERTAIN, RiskImpact.NEGLIGIBLE): "low",
    (RiskLikelihood.ALMOST_CERTAIN, RiskImpact.MINOR): "low",
    (RiskLikelihood.RARE, RiskImpact.MAJOR): "low",
    (RiskLikelihood.RARE, RiskImpact.CATASTROPHIC): "medium",
}


def calculate_residual_risk(likelihood: RiskLikelihood, impact: RiskImpact) -> str:
    """Return residual risk level from the Art. 9 risk matrix.

    Args:
        likelihood: How likely the risk is to occur.
        impact: How severe the impact would be.

    Returns:
        Risk level string: 'unacceptable', 'high', 'medium', or 'low'.
        Defaults to 'medium' for combinations not in the matrix.
    """
    return RISK_MATRIX.get((likelihood, impact), "medium")


class RiskEntry(Base):
    """Art. 9: Risk register entry per agent per tenant."""

    __tablename__ = "governance_risk_entries"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    agent_name = Column(String(200), nullable=False)
    risk_description = Column(Text, nullable=False)
    # Tekstkolom (VARCHAR(30)) en geen native enum: de migratieketen heeft nooit een enumtype
    # aangemaakt, en een native enum liet elke insert via asyncpg falen op `type "risklikelihood"
    # does not exist` (gemeten 2026-10-23, schemadrift-rapport). De waarden zijn de lowercase
    # `.value`s, gelijk aan wat `RiskEntryCreate` aanneemt; er stond nooit een rij in.
    likelihood = Column(
        SAEnum(
            RiskLikelihood,
            native_enum=False,
            length=30,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    impact = Column(
        SAEnum(
            RiskImpact,
            native_enum=False,
            length=30,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    mitigation = Column(Text, nullable=False)
    residual_risk = Column(String(50), nullable=False)
    last_reviewed = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    reviewer_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class RiskEntryCreate(BaseModel):
    agent_name: str = Field(..., max_length=200)
    risk_description: str
    likelihood: RiskLikelihood
    impact: RiskImpact
    mitigation: str
    residual_risk: str


class RiskRegister:
    """In-memory risk register for EU AI Act Art. 9 governance validation.

    Maps AI Act risk categories to the maximum permitted autonomy level.
    Call `validate_contract(contract)` before wiring a GovernanceContract into
    an agent to ensure the risk/autonomy combination is organisationally approved.
    """

    _AUTONOMY_ORDER = [
        "HUMAN_IN_LOOP",
        "HUMAN_ON_LOOP",
        "HUMAN_OUT_OF_LOOP",
        "ADVISORY",
    ]

    _DEFAULT_MAX_AUTONOMY: dict[str, str] = {
        "UNACCEPTABLE": "BLOCKED",
        "HIGH_RISK": "HUMAN_IN_LOOP",
        "LIMITED": "HUMAN_ON_LOOP",
        "MINIMAL": "HUMAN_OUT_OF_LOOP",
    }

    def __init__(self) -> None:
        self._overrides: dict[str, str] = {}

    def set_max_autonomy(self, risk_level: str, max_autonomy: str) -> None:
        """Override default policy for a specific risk level."""
        self._overrides[risk_level] = max_autonomy

    def validate_contract(self, contract: object) -> bool:
        """Return True if the contract's risk/autonomy combination is permitted.

        Args:
            contract: GovernanceContract instance (typed as object to avoid
                      circular import; uses duck-typing on risk_category and
                      autonomy_level attributes).
        """
        risk_level: str = getattr(contract, "risk_category", "LIMITED")
        if hasattr(risk_level, "value"):
            risk_level = risk_level.value  # type: ignore[assignment]

        autonomy_level: str = getattr(contract, "autonomy_level", "HUMAN_ON_LOOP")
        if hasattr(autonomy_level, "value"):
            autonomy_level = autonomy_level.value  # type: ignore[assignment]

        if risk_level == "UNACCEPTABLE":
            return False

        max_autonomy = self._overrides.get(risk_level) or self._DEFAULT_MAX_AUTONOMY.get(
            risk_level, "HUMAN_IN_LOOP"
        )
        if max_autonomy == "BLOCKED":
            return False

        order = self._AUTONOMY_ORDER
        max_idx = order.index(max_autonomy) if max_autonomy in order else 0
        actual_idx = order.index(autonomy_level) if autonomy_level in order else 0
        return actual_idx <= max_idx
