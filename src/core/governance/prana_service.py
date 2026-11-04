"""Persistent prana economy service (ADR-021).

The single source of truth for prana budgets. Enforcement is the ATOMIC charge (a
conditional UPDATE guarded by ``(total_prana - spent_prana) >= cost`` + rowcount) -- never
a read-then-write. ``has_budget`` is advisory only (a hint for the Council's
ResourceOfficer); the real gate is ``charge``. Every mutation appends a tamper-evident
row to the per-(tenant, department) hash chain in the SAME transaction.

Gate-2 conditions honoured:
- atomic conditional-UPDATE-with-rowcount as the sole enforcement point (no TOCTOU);
- debit + transaction insert in one transaction; the budget-row lock also serialises the
  chain tail read+append (no fork), with UNIQUE(tenant, dept, seq) as a backstop;
- explicit tenant_id filter on every query (never lean on the auto-WHERE hook, which skips
  INSERT); fail-closed on every error (deny/raise, never grant free budget);
- refill iterates per tenant inside TenantFilterBypass (the cross-tenant cron otherwise
  hits the fail-secure WHERE 1=0 and silently updates 0 rows);
- allocate_emergency requires an explicit authorized_by a copilot turn cannot supply.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance import prana_costs
from src.core.governance.models import PranaDepartmentBudget, PranaTransaction
from src.core.governance.prana_config import PRANA_PER_DEPARTMENT, prana_grace_floor
from src.core.governance.prana_departments import (
    CANONICAL_DEPARTMENTS,
    PranaDepartment,
    resolve_department,
)
from src.core.governance.prana_hash import compute_prana_hash

logger = logging.getLogger(__name__)


class InsufficientPranaError(Exception):
    """Raised when a (tenant, department) budget cannot cover an action's cost."""


class PranaBudgetNotFoundError(Exception):
    """Raised when no budget row exists for the given (tenant, department)."""


@dataclass(frozen=True)
class PranaChargeResult:
    """Outcome of a charge/refund/emergency, mirroring the NotificationBudget verdict shape."""

    department: str
    cost: int
    balance_after: int
    remaining: int  # total_prana - spent_prana after the mutation


class PranaService:
    """DB-backed prana economy. One instance per request/session."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # -- resolution -----------------------------------------------------------
    def resolve_department(
        self,
        action_type: str,
        action_params: dict[str, object] | None,
        tenant_default: PranaDepartment | None = None,
    ) -> PranaDepartment:
        return resolve_department(action_type, action_params, tenant_default)

    # -- advisory read (fail-closed) ------------------------------------------
    async def has_budget(
        self, tenant_id: int, department: str, action_type: str, tier: str | None = None
    ) -> bool:
        """Advisory hint for the ResourceOfficer. NOT the enforcement point.

        Fail-closed: any error (or missing budget row) -> False (deny). ``tier`` optionally
        prices the check by an explicit agent-type tier (used by the ALS path so its
        pre-check matches the charge cost); otherwise derived from ``action_type``.
        """
        cost = prana_costs.cost_for_tier(tier) if tier else prana_costs.cost_for_action(action_type)
        try:
            result = await self._db.execute(
                select(PranaDepartmentBudget.total_prana - PranaDepartmentBudget.spent_prana).where(
                    PranaDepartmentBudget.tenant_id == tenant_id,
                    PranaDepartmentBudget.department == department,
                )
            )
            available = result.scalar_one_or_none()
            return available is not None and available >= (cost - prana_grace_floor())
        except Exception as e:
            logger.error(
                "prana.has_budget failed (fail-closed deny): %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
                extra={"tenant_id": tenant_id, "department": department},
            )
            return False

    # -- atomic enforcement ---------------------------------------------------
    async def charge(
        self,
        tenant_id: int,
        department: str,
        action_type: str,
        actor_user_id: int | None = None,
        tier: str | None = None,
    ) -> PranaChargeResult:
        """Atomically debit the cost of ``action_type`` from (tenant, department).

        The conditional UPDATE is the enforcement point: it debits iff the budget covers
        the cost, and its row lock serialises the hash-chain append. Raises
        InsufficientPranaError when the budget cannot cover the cost (auto-block-at-0).
        The caller must run this inside a transaction so debit + ledger insert are atomic.

        ``tier`` optionally overrides the agent-type tier (ml/llm/vision/hybrid) used to
        price the charge; when omitted the tier is derived from ``action_type``. The ALS
        path passes an explicit tier so a specialist step is priced by its agent type
        rather than by a copilot action_type prefix.
        """
        agent_type = tier or prana_costs.tier_for_action(action_type)
        cost = prana_costs.cost_for_tier(agent_type)
        grace = prana_grace_floor()  # ADR-021: available may dip to -grace (default 0 = strict)

        # Atomic guard: debit only if available >= cost - grace (Postgres re-evaluates the
        # WHERE on the row it locks -> race-free against concurrent charges on the same row).
        result = await self._db.execute(
            update(PranaDepartmentBudget)
            .where(
                PranaDepartmentBudget.tenant_id == tenant_id,
                PranaDepartmentBudget.department == department,
                (PranaDepartmentBudget.total_prana - PranaDepartmentBudget.spent_prana)
                >= (cost - grace),
            )
            .values(
                spent_prana=PranaDepartmentBudget.spent_prana + cost,
                updated_at=datetime.now(timezone.utc),
            )
        )
        if result.rowcount != 1:  # type: ignore[attr-defined]
            # Either no budget row, or insufficient prana -> deny (fail-closed).
            raise InsufficientPranaError(
                f"tenant {tenant_id} department {department} cannot afford {cost} prana "
                f"for {action_type}"
            )

        balance_after = await self._available(tenant_id, department)
        await self._append_transaction(
            tenant_id=tenant_id,
            department=department,
            action_type=action_type,
            agent_type=agent_type,
            cost=cost,
            kind="spend",
            balance_after=balance_after,
            actor_user_id=actor_user_id,
            reason=None,
        )
        return PranaChargeResult(
            department=department, cost=cost, balance_after=balance_after, remaining=balance_after
        )

    async def refund(
        self,
        tenant_id: int,
        department: str,
        action_type: str,
        actor_user_id: int | None = None,
    ) -> PranaChargeResult:
        """Compensating credit when a charged action fails after debit (charge-before-execute
        + refund-on-failure). Clamps at 0 so a refund never inflates the budget."""
        agent_type = prana_costs.tier_for_action(action_type)
        cost = prana_costs.cost_for_tier(agent_type)
        result = await self._db.execute(
            update(PranaDepartmentBudget)
            .where(
                PranaDepartmentBudget.tenant_id == tenant_id,
                PranaDepartmentBudget.department == department,
            )
            .values(
                spent_prana=func.greatest(PranaDepartmentBudget.spent_prana - cost, 0),
                updated_at=datetime.now(timezone.utc),
            )
        )
        if result.rowcount != 1:  # type: ignore[attr-defined]
            raise PranaBudgetNotFoundError(
                f"no budget row for tenant {tenant_id} dept {department}"
            )
        balance_after = await self._available(tenant_id, department)
        await self._append_transaction(
            tenant_id=tenant_id,
            department=department,
            action_type=action_type,
            agent_type=agent_type,
            cost=cost,
            kind="refund",
            balance_after=balance_after,
            actor_user_id=actor_user_id,
            reason=None,
        )
        return PranaChargeResult(
            department=department, cost=cost, balance_after=balance_after, remaining=balance_after
        )

    async def allocate_emergency(
        self,
        tenant_id: int,
        department: str,
        amount: int,
        authorized_by: int,
        reason: str,
    ) -> PranaChargeResult:
        """Grant extra prana to a (tenant, department). Privileged.

        Requires an explicit ``authorized_by`` (a real user id from a PRANA_MANAGE-gated
        caller) that a copilot turn cannot supply -- so this method cannot silently become
        an ungated escalation path if a router is wired carelessly. Writes an emergency
        ledger row recording the actor + reason.
        """
        if not authorized_by or amount <= 0:
            raise ValueError("allocate_emergency requires authorized_by and a positive amount")
        result = await self._db.execute(
            update(PranaDepartmentBudget)
            .where(
                PranaDepartmentBudget.tenant_id == tenant_id,
                PranaDepartmentBudget.department == department,
            )
            .values(
                total_prana=PranaDepartmentBudget.total_prana + amount,
                updated_at=datetime.now(timezone.utc),
            )
        )
        if result.rowcount != 1:  # type: ignore[attr-defined]
            raise PranaBudgetNotFoundError(
                f"no budget row for tenant {tenant_id} dept {department}"
            )
        balance_after = await self._available(tenant_id, department)
        await self._append_transaction(
            tenant_id=tenant_id,
            department=department,
            action_type="emergency_allocation",
            agent_type="n/a",
            cost=amount,
            kind="emergency",
            balance_after=balance_after,
            actor_user_id=authorized_by,
            reason=reason,
        )
        logger.warning(
            "prana.emergency_allocation: tenant=%s dept=%s amount=%s by=%s",
            tenant_id,
            department,
            amount,
            authorized_by,
        )
        return PranaChargeResult(
            department=department,
            cost=amount,
            balance_after=balance_after,
            remaining=balance_after,
        )

    async def get_balances(self, tenant_id: int) -> list[PranaDepartmentBudget]:
        """All department budgets for a tenant (tenant-scoped)."""
        result = await self._db.execute(
            select(PranaDepartmentBudget).where(PranaDepartmentBudget.tenant_id == tenant_id)
        )
        return list(result.scalars().all())

    async def refill_all(self) -> int:
        """Idempotent daily reset of EVERY department budget to its total (spent -> 0).

        Cross-tenant maintenance job: runs inside TenantFilterBypass because the auto-WHERE
        hook is fail-secure -- without tenant context it rewrites the SELECT/UPDATE to
        WHERE 1=0 and would silently touch 0 rows. Resetting to a fixed value (not an
        additive credit) makes this safe to run more than once (idempotent balance). Returns
        the number of budgets reset.
        """
        from src.core.database.tenant_query_filter import TenantFilterBypass

        now = datetime.now(timezone.utc)
        count = 0
        with TenantFilterBypass():
            result = await self._db.execute(select(PranaDepartmentBudget))
            for budget in result.scalars().all():
                budget.spent_prana = 0
                budget.allocated_prana = 0
                budget.cycle_start = now
                budget.updated_at = now
                await self._append_transaction(
                    tenant_id=budget.tenant_id,
                    department=budget.department,
                    action_type="daily_refill",
                    agent_type="n/a",
                    cost=budget.total_prana,
                    kind="refill",
                    balance_after=budget.total_prana,
                    actor_user_id=None,
                    reason="daily reset",
                )
                count += 1
        await self._db.flush()
        return count

    async def provision_tenant(self, tenant_id: int) -> int:
        """Idempotently seed a budget row (PRANA_PER_DEPARTMENT) for every canonical
        department of a tenant, each with a genesis funding ledger entry. Safe to call more
        than once (existing departments are skipped). Returns the number of departments
        newly created. Called from the tenant-provisioning paths in best_effort."""
        existing = await self._db.execute(
            select(PranaDepartmentBudget.department).where(
                PranaDepartmentBudget.tenant_id == tenant_id
            )
        )
        have = {row[0] for row in existing.all()}
        created = 0
        for dept in sorted(CANONICAL_DEPARTMENTS, key=lambda d: d.value):
            if dept.value in have:
                continue
            self._db.add(
                PranaDepartmentBudget(
                    tenant_id=tenant_id,
                    department=dept.value,
                    total_prana=PRANA_PER_DEPARTMENT,
                    spent_prana=0,
                )
            )
            await self._db.flush()
            await self._append_transaction(
                tenant_id=tenant_id,
                department=dept.value,
                action_type="provisioning",
                agent_type="n/a",
                cost=PRANA_PER_DEPARTMENT,
                kind="refill",  # initial funding == a refill to full (allowed by ck_prana_tx_kind)
                balance_after=PRANA_PER_DEPARTMENT,
                actor_user_id=None,
                reason="initial provisioning",
            )
            created += 1
        return created

    # -- internals ------------------------------------------------------------
    async def _available(self, tenant_id: int, department: str) -> int:
        result = await self._db.execute(
            select(PranaDepartmentBudget.total_prana - PranaDepartmentBudget.spent_prana).where(
                PranaDepartmentBudget.tenant_id == tenant_id,
                PranaDepartmentBudget.department == department,
            )
        )
        return int(result.scalar_one())

    async def _append_transaction(
        self,
        *,
        tenant_id: int,
        department: str,
        action_type: str,
        agent_type: str,
        cost: int,
        kind: str,
        balance_after: int,
        actor_user_id: int | None,
        reason: str | None,
    ) -> None:
        """Append a hash-chained ledger row. Runs after the budget UPDATE so the row lock
        serialises the per-(tenant, department) chain tail."""
        tail = await self._db.execute(
            select(PranaTransaction.sequence_no, PranaTransaction.hash)
            .where(
                PranaTransaction.tenant_id == tenant_id,
                PranaTransaction.department == department,
            )
            .order_by(PranaTransaction.sequence_no.desc())
            .limit(1)
        )
        row = tail.first()
        prev_seq, prev_hash = (row[0], row[1]) if row else (0, None)
        seq = prev_seq + 1
        created_at = datetime.now(timezone.utc)
        digest = compute_prana_hash(
            tenant_id=tenant_id,
            department=department,
            action_type=action_type,
            cost=cost,
            kind=kind,
            actor_user_id=actor_user_id,
            balance_after=balance_after,
            created_at=created_at.isoformat(),
            previous_hash=prev_hash,
        )
        self._db.add(
            PranaTransaction(
                tenant_id=tenant_id,
                department=department,
                sequence_no=seq,
                action_type=action_type,
                agent_type=agent_type,
                cost=cost,
                kind=kind,
                balance_after=balance_after,
                actor_user_id=actor_user_id,
                reason=reason,
                created_at=created_at,
                previous_hash=prev_hash,
                hash=digest,
            )
        )
        await self._db.flush()
