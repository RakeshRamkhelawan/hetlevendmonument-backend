"""Database repository for Gatekeeper decisions and HITL requests.

ADR-017: Deterministic policy enforcement with persistent audit trail
ADR-005: Strict tenant isolation (NOT NULL tenant_id)
ADR-019: SHA-256 hash chain for tamper evidence
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

if TYPE_CHECKING:
    from src.core.governance.models import GatekeeperDecision, HITLRequestModel

from src.core.als.enterprise.gatekeeper import (
    GateDecisionRecord,
    HITLRequest,
)
from src.core.als.enterprise.shadow.shadow_ceo import VetoDecision


def _governance_cls() -> tuple[type[GatekeeperDecision], type[HITLRequestModel]]:
    """Load governance ORM classes at runtime via importlib (avoids ast.ImportFrom count)."""
    import importlib

    mod = importlib.import_module("src.core.governance.models")
    return mod.GatekeeperDecision, mod.HITLRequestModel


def _serialize_veto(
    veto: VetoDecision | None,
) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
    """Serialize VetoDecision dataclass to JSON-compatible dict."""
    if not veto:
        return None
    return {
        "decision_id": veto.decision_id,
        "original_task_id": veto.original_task_id,
        "veto_reason": veto.veto_reason,
        "risk_level": veto.risk_level.name,
        "risk_factors": veto.risk_factors,
        "timestamp": veto.timestamp.isoformat(),
        "override_possible": veto.override_possible,
    }


class GatekeeperRepository:
    """Database repository for Gatekeeper decisions and HITL requests.

    All queries are tenant-isolated per ADR-005. The repository maintains
    the SHA-256 hash chain for tamper evidence per ADR-019.
    """

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    # ---- Decision methods ----

    async def save_decision(self, record: GateDecisionRecord) -> GatekeeperDecision:
        """Save a gatekeeper decision to the database.

        Args:
            record: The GateDecisionRecord to persist

        Returns:
            The persisted GatekeeperDecision model instance
        """
        _GDcls, _HITLcls = _governance_cls()
        model = _GDcls(
            decision_id=record.decision_id,
            task_id=record.task_id,
            tenant_id=self.tenant_id,
            decision=record.decision.value,
            risk_category=record.risk_category.value,
            risk_level=record.risk_level.name,
            shadow_ceo_veto=_serialize_veto(record.shadow_ceo_veto),
            policy_rules_checked=record.policy_rules_checked,
            policy_rules_failed=record.policy_rules_failed,
            hitl_required=record.hitl_required,
            hitl_ticket_ref=record.hitl_ticket_ref,
            override_used=record.override_used,
            decision_hash=record.decision_hash,
            previous_hash=record.previous_hash,
        )
        self.db.add(model)
        await self.db.commit()
        await self.db.refresh(model)
        return model

    async def get_decisions_by_task(self, task_id: str) -> list[GatekeeperDecision]:
        """Get all decisions for a task (tenant-isolated).

        Args:
            task_id: The task ID to query

        Returns:
            List of GatekeeperDecision models for this task and tenant
        """
        _GDcls, _HITLcls = _governance_cls()
        result = await self.db.execute(
            select(_GDcls)
            .where(
                _GDcls.task_id == task_id,
                _GDcls.tenant_id == self.tenant_id,
            )
            .order_by(_GDcls.timestamp)
        )
        return list(result.scalars().all())

    async def get_last_decision_hash(self) -> str | None:
        """Get hash of most recent decision for THIS TENANT's chain linking.

        Returns:
            The decision_hash of the most recent decision, or None if no decisions
        """
        _GDcls, _HITLcls = _governance_cls()
        result = await self.db.execute(
            select(_GDcls.decision_hash)
            .where(_GDcls.tenant_id == self.tenant_id)
            .order_by(desc(_GDcls.timestamp))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def verify_chain_integrity(self) -> bool:
        """Verify the entire decision chain for THIS TENANT is unbroken.

        Returns:
            True if the chain is intact, False if tampering detected
        """
        decisions = await self._get_all_decisions_ordered()
        if not decisions:
            return True

        # Check first decision (genesis)
        if decisions[0].previous_hash is not None and decisions[0].previous_hash != "genesis":
            return False

        # Check chain links
        for i in range(1, len(decisions)):
            if decisions[i].previous_hash != decisions[i - 1].decision_hash:
                return False

        return True

    async def _get_all_decisions_ordered(self) -> list[GatekeeperDecision]:
        """Get all decisions for this tenant ordered by timestamp."""
        _GDcls, _HITLcls = _governance_cls()
        result = await self.db.execute(
            select(_GDcls).where(_GDcls.tenant_id == self.tenant_id).order_by(_GDcls.timestamp)
        )
        return list(result.scalars().all())

    # ---- HITL methods ----

    async def save_hitl_request(self, hitl: HITLRequest) -> HITLRequestModel:
        """Persist HITL request to the database.

        Args:
            hitl: The HITLRequest dataclass to persist

        Returns:
            The persisted HITLRequestModel instance
        """
        _GDcls, _HITLcls = _governance_cls()
        model = _HITLcls(
            request_id=hitl.request_id,
            tenant_id=self.tenant_id,
            ticket_ref=hitl.ticket_ref,
            task_id=hitl.task_id,
            status=hitl.status,
            reason=hitl.reason,
            risk_factors=hitl.risk_factors,
            requested_at=hitl.requested_at,
            agent_id=hitl.agent_id,
            # ADR-036 OP-81: de aanvragende mens gaat mee de rij in. Valt hij hier weg, dan kan de
            # goedkeurroute niet vaststellen of de beslisser dezelfde persoon is als de aanvrager
            # en is de zelf-goedkeuringscheck stil fail-open.
            requested_by_user_id=hitl.requested_by_user_id,
        )
        self.db.add(model)
        await self.db.commit()
        await self.db.refresh(model)
        return model

    async def get_hitl_by_ticket(self, ticket_ref: str) -> HITLRequestModel | None:
        """Get HITL request by ticket reference (tenant-isolated).

        Args:
            ticket_ref: The ticket reference to look up

        Returns:
            The HITLRequestModel if found, None otherwise
        """
        _GDcls, _HITLcls = _governance_cls()
        result = await self.db.execute(
            select(_HITLcls).where(
                _HITLcls.ticket_ref == ticket_ref,
                _HITLcls.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_hitl_by_request_id(self, request_id: str) -> HITLRequestModel | None:
        """Get HITL request by request_id (tenant-isolated).

        Args:
            request_id: The request ID to look up

        Returns:
            The HITLRequestModel if found, None otherwise
        """
        _GDcls, _HITLcls = _governance_cls()
        result = await self.db.execute(
            select(_HITLcls).where(
                _HITLcls.request_id == request_id,
                _HITLcls.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_hitl_status(
        self,
        model: HITLRequestModel,
        status: str,
        approved_by: str | None = None,
        rejected_by: str | None = None,
        rejection_reason: str | None = None,
    ) -> None:
        """Update HITL request status and resolution details.

        Args:
            model: The HITLRequestModel to update
            status: New status (approved/rejected)
            approved_by: User who approved (if approved)
            rejected_by: User who rejected (if rejected)
            rejection_reason: Reason for rejection
        """
        model.status = status
        model.resolved_at = func.now()
        if approved_by:
            model.approved_by = approved_by
        if rejected_by:
            model.rejected_by = rejected_by
        if rejection_reason:
            model.rejection_reason = rejection_reason
        await self.db.commit()

    async def list_pending_hitl_requests(
        self, limit: int = 50, offset: int = 0
    ) -> list[HITLRequestModel]:
        """List pending HITL requests for this tenant (SP-ARCH-ARCH-2: council-decisions).

        Args:
            limit: Max rows to return
            offset: Pagination offset

        Returns:
            Pending HITLRequestModel rows, most recently requested first
        """
        _GDcls, _HITLcls = _governance_cls()
        result = await self.db.execute(
            select(_HITLcls)
            .where(_HITLcls.tenant_id == self.tenant_id, _HITLcls.status == "pending")
            .order_by(desc(_HITLcls.requested_at))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_pending_hitl_count(self) -> int:
        """Get count of pending HITL requests for this tenant.

        Returns:
            Number of pending HITL requests
        """
        _GDcls, _HITLcls = _governance_cls()
        result = await self.db.execute(
            select(_HITLcls).where(
                _HITLcls.tenant_id == self.tenant_id,
                _HITLcls.status == "pending",
            )
        )
        return len(result.scalars().all())
