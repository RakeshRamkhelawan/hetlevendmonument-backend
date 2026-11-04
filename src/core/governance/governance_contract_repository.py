"""Database repository for GovernanceContract persistence.

ADR-031: governance contract binds an agent_id to autonomy level, risk
category, and compliance evidence -- must survive process restarts so HITL
approvals recorded via record_hitl_approval() are not lost.
ADR-005: strict tenant isolation (NOT NULL tenant_id).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.governance_contract import AutonomyLevel, GovernanceContract
from src.core.shared.ai_act_types import AIActRiskLevel

if TYPE_CHECKING:
    from src.core.governance.models import AgentGovernanceContract


def _model_cls() -> type[AgentGovernanceContract]:
    """Load the ORM class at runtime via importlib (avoids ast.ImportFrom count)."""
    import importlib

    mod = importlib.import_module("src.core.governance.models")
    return cast("type[AgentGovernanceContract]", mod.AgentGovernanceContract)


class GovernanceContractRepository:
    """Loads and saves GovernanceContract state, tenant-isolated per ADR-005."""

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    async def load(self, agent_id: str) -> GovernanceContract | None:
        """Load a persisted contract for this tenant + agent_id, or None."""
        model_cls = _model_cls()
        result = await self.db.execute(
            select(model_cls).where(
                model_cls.agent_id == agent_id,
                model_cls.tenant_id == self.tenant_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return GovernanceContract(
            agent_id=row.agent_id,
            tenant_id=row.tenant_id,
            autonomy_level=AutonomyLevel(row.autonomy_level),
            risk_category=AIActRiskLevel(row.risk_category),
            evidence=dict(row.evidence),
            created_at=row.created_at,
        )

    async def load_or_create(self, agent_id: str) -> GovernanceContract:
        """Load a persisted contract, or create+save a conservative default.

        The default (HUMAN_IN_LOOP/LIMITED) matches GovernanceContract's own
        dataclass defaults -- callers that already know an agent's real AI Act
        classification (e.g. agent construction) should prefer load() and fall
        back to their own classify_agent() result instead of this default.
        """
        existing = await self.load(agent_id)
        if existing is not None:
            return existing
        contract = GovernanceContract(agent_id=agent_id, tenant_id=self.tenant_id)
        await self.save(contract)
        return contract

    async def save(self, contract: GovernanceContract) -> None:
        """Upsert the contract's current state (autonomy/risk/evidence).

        Uses INSERT ... ON CONFLICT DO UPDATE (single atomic statement) instead
        of SELECT-then-branch: two concurrent approvals for the same agent_id
        would otherwise both see no existing row and race to INSERT, with the
        loser raising IntegrityError on the (tenant_id, agent_id) unique
        constraint instead of merging.
        """
        model_cls = _model_cls()
        stmt = pg_insert(model_cls).values(
            tenant_id=self.tenant_id,
            agent_id=contract.agent_id,
            autonomy_level=contract.autonomy_level.value,
            risk_category=contract.risk_category.value,
            evidence=contract.evidence,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["tenant_id", "agent_id"],
            set_={
                "autonomy_level": stmt.excluded.autonomy_level,
                "risk_category": stmt.excluded.risk_category,
                "evidence": stmt.excluded.evidence,
            },
        )
        await self.db.execute(stmt)
        await self.db.commit()
