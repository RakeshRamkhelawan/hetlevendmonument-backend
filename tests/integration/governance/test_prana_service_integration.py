"""PostgreSQL integration tests for PranaService (ADR-021 Fase 1).

Covers the Gate-2 CRITICAL/HIGH items with real DB behaviour (bound values, not string
matching): atomic charge as the sole gate (no oversell, no negative balance), true
concurrency, per-(tenant,department) tenant isolation, hash-chain integrity, idempotent
refill, and fail-closed on DB error.

ADR-036 register: `test_refill_all_resets_every_tenant_idempotently` is de evidence voor
OP-139's sluiting (er bestaat nu een dagelijks bijvulpad); `test_concurrent_charges_do_not_oversell`
is de evidence voor OP-141's sluiting (de atomaire, voorwaardelijke UPDATE in `charge()` is nu
de ENIGE afdwingpunt -- de eerdere check-then-act-race tussen een losse controle en een losse
afrekening bestaat niet meer, want een verouderd `has_budget()`-advies wordt bij `charge()`
zelf opnieuw en atomisch beoordeeld).
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.governance.models import PranaDepartmentBudget, PranaTransaction
from src.core.governance.prana_service import InsufficientPranaError, PranaService
from src.core.models.rbac_models import Tenant

pytestmark = [pytest.mark.integration, pytest.mark.security, pytest.mark.multi_tenant]


async def _seed_tenant(session: AsyncSession, suffix: str) -> int:
    tenant = Tenant(name=f"Prana Tenant {suffix}", slug=f"prana-tenant-{suffix}")
    session.add(tenant)
    await session.flush()
    return tenant.id


async def _seed_budget(
    session: AsyncSession, tenant_id: int, department: str, total: int = 100
) -> None:
    session.add(
        PranaDepartmentBudget(
            tenant_id=tenant_id, department=department, total_prana=total, spent_prana=0
        )
    )
    await session.flush()


async def test_charge_debits_and_writes_hash_chained_ledger(
    postgres_session: AsyncSession,
) -> None:
    tenant_id = await _seed_tenant(postgres_session, "charge")
    await _seed_budget(postgres_session, tenant_id, "finance", total=100)
    svc = PranaService(postgres_session)

    # create_task -> llm tier -> cost 50.
    r1 = await svc.charge(tenant_id, "finance", "create_task", actor_user_id=5)
    assert r1.cost == 50
    assert r1.balance_after == 50

    # ledger: one spend row, sequence 1, hash present, previous_hash genesis (None).
    txs = (
        (
            await postgres_session.execute(
                select(PranaTransaction).where(PranaTransaction.tenant_id == tenant_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(txs) == 1
    assert txs[0].sequence_no == 1 and txs[0].kind == "spend" and txs[0].cost == 50
    assert txs[0].previous_hash is None and len(txs[0].hash) == 64

    # second charge chains onto the first.
    await svc.charge(tenant_id, "finance", "list_tasks", actor_user_id=5)  # ml tier -> 10
    txs2 = (
        (
            await postgres_session.execute(
                select(PranaTransaction)
                .where(PranaTransaction.tenant_id == tenant_id)
                .order_by(PranaTransaction.sequence_no)
            )
        )
        .scalars()
        .all()
    )
    assert [t.sequence_no for t in txs2] == [1, 2]
    assert txs2[1].previous_hash == txs2[0].hash  # chain links


async def test_charge_insufficient_raises_and_does_not_mutate(
    postgres_session: AsyncSession,
) -> None:
    tenant_id = await _seed_tenant(postgres_session, "insuff")
    await _seed_budget(postgres_session, tenant_id, "hr", total=40)  # < 50 (llm)
    svc = PranaService(postgres_session)

    with pytest.raises(InsufficientPranaError):
        await svc.charge(tenant_id, "hr", "create_task")  # cost 50 > 40

    # Fail-closed: no debit, no ledger row.
    budget = (
        await postgres_session.execute(
            select(PranaDepartmentBudget).where(PranaDepartmentBudget.tenant_id == tenant_id)
        )
    ).scalar_one()
    assert budget.spent_prana == 0
    txs = (
        (
            await postgres_session.execute(
                select(PranaTransaction).where(PranaTransaction.tenant_id == tenant_id)
            )
        )
        .scalars()
        .all()
    )
    assert txs == []


async def test_tenant_isolation_charge_does_not_touch_other_tenant(
    postgres_session: AsyncSession,
) -> None:
    """Bound-value: charging tenant A leaves tenant B's identical budget untouched."""
    a = await _seed_tenant(postgres_session, "iso-a")
    b = await _seed_tenant(postgres_session, "iso-b")
    await _seed_budget(postgres_session, a, "finance", total=100)
    await _seed_budget(postgres_session, b, "finance", total=100)
    svc = PranaService(postgres_session)

    await svc.charge(a, "finance", "create_task")  # 50 off A

    balances_a = {x.department: x.spent_prana for x in await svc.get_balances(a)}
    balances_b = {x.department: x.spent_prana for x in await svc.get_balances(b)}
    assert balances_a["finance"] == 50
    assert balances_b["finance"] == 0  # B untouched
    # get_balances(A) never returns B's rows.
    assert all(row.tenant_id == a for row in await svc.get_balances(a))


async def test_refill_all_resets_every_tenant_idempotently(
    postgres_session: AsyncSession,
) -> None:
    a = await _seed_tenant(postgres_session, "refill-a")
    b = await _seed_tenant(postgres_session, "refill-b")
    await _seed_budget(postgres_session, a, "finance", total=100)
    await _seed_budget(postgres_session, b, "hr", total=100)
    svc = PranaService(postgres_session)
    await svc.charge(a, "finance", "create_task")  # spend 50
    await svc.charge(b, "hr", "list_tasks")  # spend 10

    n1 = await svc.refill_all()
    assert n1 == 2
    # Running twice yields the same balances (idempotent reset).
    await svc.refill_all()

    for tenant_id in (a, b):
        for row in await svc.get_balances(tenant_id):
            assert row.spent_prana == 0, (tenant_id, row.department)


async def test_has_budget_is_fail_closed_on_db_error() -> None:
    """A broken DB session must make the advisory has_budget deny (never grant)."""

    class _BoomSession:
        async def execute(self, *a, **k):
            raise RuntimeError("db down")

    svc = PranaService(_BoomSession())  # type: ignore[arg-type]
    assert await svc.has_budget(1, "finance", "create_task") is False


async def test_provision_tenant_seeds_all_departments_idempotently(
    postgres_session: AsyncSession,
) -> None:
    """provision_tenant seeds 10000 for every canonical department, with a genesis funding
    ledger row, and is safe to run twice (idempotent)."""
    from src.core.governance.prana_departments import CANONICAL_DEPARTMENTS

    tenant_id = await _seed_tenant(postgres_session, "prov")
    svc = PranaService(postgres_session)

    n1 = await svc.provision_tenant(tenant_id)
    assert n1 == len(CANONICAL_DEPARTMENTS)

    balances = await svc.get_balances(tenant_id)
    assert len(balances) == len(CANONICAL_DEPARTMENTS)
    assert all(b.total_prana == 10000 and b.spent_prana == 0 for b in balances)

    # Idempotent: a second run creates nothing and does not duplicate rows.
    assert await svc.provision_tenant(tenant_id) == 0
    assert len(await svc.get_balances(tenant_id)) == len(CANONICAL_DEPARTMENTS)

    # One genesis funding (kind=refill) ledger row per department.
    txs = (
        (
            await postgres_session.execute(
                select(PranaTransaction).where(PranaTransaction.tenant_id == tenant_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(txs) == len(CANONICAL_DEPARTMENTS)
    assert all(t.kind == "refill" and t.balance_after == 10000 for t in txs)


async def test_grace_floor_allows_bounded_negative_balance(
    postgres_session: AsyncSession, monkeypatch
) -> None:
    """ADR-021 grace: with a grace floor, a charge may take the balance bounded-negative;
    without it (default 0) the same charge is denied (strict auto-block)."""
    tenant_id = await _seed_tenant(postgres_session, "grace")
    await _seed_budget(postgres_session, tenant_id, "finance", total=40)  # < 50 (llm)
    svc = PranaService(postgres_session)

    # Strict (grace 0): 40 < 50 -> denied.
    monkeypatch.setenv("PRANA_GRACE_FLOOR", "0")
    with pytest.raises(InsufficientPranaError):
        await svc.charge(tenant_id, "finance", "create_task")

    # Grace 20: threshold 50-20=30 <= 40 -> allowed, balance dips to -10.
    monkeypatch.setenv("PRANA_GRACE_FLOOR", "20")
    r = await svc.charge(tenant_id, "finance", "create_task")
    assert r.balance_after == -10  # 40 - 50, within the -20 grace floor


async def test_refill_job_resets_budgets(postgres_session: AsyncSession, monkeypatch) -> None:
    """run_prana_refill (the Dramatiq actor's delegate) resets budgets and reports the count.

    The job opens its own db_manager session; point that at the test session so the run
    executes inside the fixture's transaction.
    """
    from src.core.jobs import prana_refill_job

    tenant_id = await _seed_tenant(postgres_session, "refilljob")
    await _seed_budget(postgres_session, tenant_id, "finance", total=100)
    await PranaService(postgres_session).charge(tenant_id, "finance", "create_task")  # spend 50

    class _Ctx:
        async def __aenter__(self):
            return postgres_session

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(prana_refill_job.db_manager, "get_session", lambda: _Ctx())

    result = await prana_refill_job.run_prana_refill()
    assert result["reset"] >= 1

    balances = {
        b.department: b.spent_prana
        for b in await PranaService(postgres_session).get_balances(tenant_id)
    }
    assert balances["finance"] == 0


async def test_full_economy_lifecycle(postgres_session: AsyncSession) -> None:
    """End-to-end economy loop at the service level: provision -> has_budget -> charge ->
    exhaust -> auto-block (has_budget False) -> refill -> has_budget True again."""
    tenant_id = await _seed_tenant(postgres_session, "lifecycle")
    svc = PranaService(postgres_session)
    # Small budget so we can exhaust it deterministically: 2x a 50-cost create_task.
    await _seed_budget(postgres_session, tenant_id, "finance", total=100)

    assert await svc.has_budget(tenant_id, "finance", "create_task") is True
    await svc.charge(tenant_id, "finance", "create_task")  # 50 -> available 50
    await svc.charge(tenant_id, "finance", "create_task")  # 50 -> available 0

    # Exhausted: has_budget False (auto-block) and a further charge is denied.
    assert await svc.has_budget(tenant_id, "finance", "create_task") is False
    with pytest.raises(InsufficientPranaError):
        await svc.charge(tenant_id, "finance", "create_task")

    # Refill restores the budget; the loop can run again.
    await svc.refill_all()
    assert await svc.has_budget(tenant_id, "finance", "create_task") is True
    budget = {b.department: b.spent_prana for b in await svc.get_balances(tenant_id)}
    assert budget["finance"] == 0


async def test_concurrent_charges_do_not_oversell(postgres_engine: AsyncEngine) -> None:
    """Two concurrent charges on a budget that covers only ONE must not drive it negative.

    Seeds met een EIGEN sessie en een ECHTE commit (de gedeelde `postgres_session`-fixture
    rolt terug via een savepoint, dus zijn schrijfacties zijn onzichtbaar voor een aparte
    verbinding), en draait daarna twee charges op onafhankelijke sessies zodat de
    row-level lock van de conditionele UPDATE ze werkelijk serialiseert. Ruimt op in
    `finally`.

    **Waarom deze test de `postgres_engine`-fixture neemt en niet zijn eigen engine bouwt
    (ADR-036 OP-219, gemeten 2026-09-09).** Hier stond `create_async_engine(
    os.environ["DATABASE_URL"])`. Dat is een LEESACTIE OP EEN VERANDERLIJKE OMGEVING tijdens
    de testrun, en die omgeving wordt door een andere testmodule overschreven:
    `tests/integration/test_middleware_order_fix.py:15` zet `DATABASE_URL` op
    `sqlite+aiosqlite:///:memory:` op MODULENIVEAU, dus tijdens de collectie, en dat geldt
    daarna voor de hele sessie. Gevolg in CI-run 34345468723:
    `sqlite3.OperationalError: no such table: tenants`. Deze test was de ENIGE in dit bestand
    die geen fixture nam, en daarmee ook de enige die de PostgreSQL-beschikbaarheidscheck van
    de suite oversloeg -- alle zustertests waren daarom groen.

    `postgres_engine` (`tests/integration/conftest.py:810`) leunt op de moduleconstante
    `TEST_DB_URL`, die bij import wordt vastgelegd en dus NIET door een latere
    omgevingswijziging te vergiftigen is. Hij gebruikt `NullPool`, dus elke sessie uit de
    sessionmaker hieronder krijgt nog steeds een eigen verbinding -- precies wat de row-level
    lock nodig heeft. De vervuiler zelf staat als OP-219 open; die opruimen raakt mogelijk
    andere tests en hoort een eigen CI-run te krijgen.
    """
    import uuid as _uuid

    from src.core.middleware.tenant_context import set_tenant_id

    maker = async_sessionmaker(postgres_engine, expire_on_commit=False)
    tenant_id: int | None = None
    try:
        async with maker() as s:
            tenant = Tenant(name="Prana Race", slug=f"prana-race-{_uuid.uuid4().hex[:8]}")
            s.add(tenant)
            await s.flush()
            tenant_id = tenant.id
            s.add(
                PranaDepartmentBudget(
                    tenant_id=tenant_id, department="finance", total_prana=50, spent_prana=0
                )
            )
            await s.commit()

        async def _try_charge() -> str:
            async with maker() as s:
                # Production sets tenant context from the JWT; mirror that so the
                # auto-WHERE hook (if active in this process) does not fail-secure to 0 rows.
                set_tenant_id(tenant_id)
                try:
                    await PranaService(s).charge(tenant_id, "finance", "create_task")
                    await s.commit()
                    return "ok"
                except InsufficientPranaError:
                    await s.rollback()
                    return "denied"

        results = await asyncio.gather(_try_charge(), _try_charge())
        assert sorted(results) == ["denied", "ok"], results  # exactly one succeeds

        async with maker() as s:
            set_tenant_id(tenant_id)
            budget = (
                await s.execute(
                    select(PranaDepartmentBudget).where(
                        PranaDepartmentBudget.tenant_id == tenant_id
                    )
                )
            ).scalar_one()
            assert budget.spent_prana == 50  # exactly one 50-charge, never negative
            assert budget.total_prana - budget.spent_prana == 0
    finally:
        if tenant_id is not None:
            async with maker() as s:
                await s.execute(
                    text("DELETE FROM prana_transaction WHERE tenant_id = :t"), {"t": tenant_id}
                )
                await s.execute(
                    text("DELETE FROM prana_department_budget WHERE tenant_id = :t"),
                    {"t": tenant_id},
                )
                await s.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": tenant_id})
                await s.commit()
