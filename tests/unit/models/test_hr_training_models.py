"""De trainings-tabellen achter Fase 3 (BE-AGT-058, vervolg op ADR-036 OP-26).

De skills-gap-analyse (`analyze_skill_gap`) kan een tekort aan een vaardigheid melden, maar er
was nergens een tabel die een training aan die vaardigheid koppelt, of bijhoudt wie een
training heeft gevolgd. `trainings` is de catalogus (analoog aan `skills`); `employee_trainings`
is de koppeling naar wie wat heeft gedaan (analoog aan `employee_skills`).

Cascade-gedrag (`ondelete=CASCADE`/`SET NULL`) wordt hier NIET getoetst -- SQLite handhaaft
foreign-key-acties alleen met `PRAGMA foreign_keys=ON`, wat deze fixture niet zet (zelfde
beperking als `tests/unit/test_account_lockout_model.py::test_cascade_delete`). Dat bewijs
levert de Postgres-migratieproef (Dag 1, zie het sprintplan) apart.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# BEWUST op moduleniveau, niet in een fixture of testfunctie: de `db_session`-fixture
# (`tests/fixtures/database.py`) bouwt het schema via `Base.metadata.create_all` zodra hij
# voor het eerst gebruikt wordt, en ziet dan alleen de modellen die op dat moment al
# geimporteerd zijn. Zelfde patroon en reden als `tests/unit/tool_broker/test_hr_skill_gap.py`.
from src.core.models.hr_skills_models import Skill
from src.core.models.hr_training_models import EmployeeTraining, Training
from src.core.models.rbac_models import Tenant, User


async def _make_tenant(session: AsyncSession, tenant_id: int, slug: str) -> Tenant:
    tenant = Tenant(id=tenant_id, name=f"Tenant {slug}", slug=slug)
    session.add(tenant)
    await session.flush()
    return tenant


async def _make_user(session: AsyncSession, tenant_id: int, slug: str) -> User:
    user = User(
        tenant_id=tenant_id,
        email=f"{slug}@example.test",
        hashed_password="x",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_training_requires_unique_name_per_tenant(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "uniq-name")
    db_session.add(Training(tenant_id=1, name="Excel Basics"))
    await db_session.commit()

    db_session.add(Training(tenant_id=1, name="Excel Basics"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_training_allows_same_name_across_different_tenants(
    db_session: AsyncSession,
) -> None:
    await _make_tenant(db_session, 1, "cross-a")
    await _make_tenant(db_session, 2, "cross-b")

    db_session.add(Training(tenant_id=1, name="IFRS Certification"))
    db_session.add(Training(tenant_id=2, name="IFRS Certification"))
    await db_session.commit()

    assert True  # geen IntegrityError -- de unique-constraint is per tenant, niet globaal


@pytest.mark.asyncio
async def test_training_skill_id_is_optional(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "no-skill")
    training = Training(tenant_id=1, name="Onboarding")
    db_session.add(training)
    await db_session.commit()

    assert training.skill_id is None


@pytest.mark.asyncio
async def test_training_can_link_to_a_real_skill(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "linked-skill")
    skill = Skill(tenant_id=1, name="IFRS")
    db_session.add(skill)
    await db_session.flush()

    training = Training(tenant_id=1, name="IFRS Certification", skill_id=skill.id)
    db_session.add(training)
    await db_session.commit()

    assert training.skill_id == skill.id


@pytest.mark.asyncio
async def test_employee_training_requires_unique_user_training_pair(
    db_session: AsyncSession,
) -> None:
    await _make_tenant(db_session, 1, "uniq-et")
    user = await _make_user(db_session, 1, "uniq-et-user")
    training = Training(tenant_id=1, name="Onboarding")
    db_session.add(training)
    await db_session.flush()

    db_session.add(EmployeeTraining(tenant_id=1, user_id=user.id, training_id=training.id))
    await db_session.commit()

    db_session.add(EmployeeTraining(tenant_id=1, user_id=user.id, training_id=training.id))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_employee_training_status_defaults_to_assigned(
    db_session: AsyncSession,
) -> None:
    await _make_tenant(db_session, 1, "default-status")
    user = await _make_user(db_session, 1, "default-status-user")
    training = Training(tenant_id=1, name="Onboarding")
    db_session.add(training)
    await db_session.flush()

    row = EmployeeTraining(tenant_id=1, user_id=user.id, training_id=training.id)
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    assert row.status == "assigned"
    assert row.completed_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["assigned", "in_progress", "completed"])
async def test_employee_training_accepts_each_valid_status(
    db_session: AsyncSession, status: str
) -> None:
    await _make_tenant(db_session, 1, f"valid-{status}")
    user = await _make_user(db_session, 1, f"valid-{status}-user")
    training = Training(tenant_id=1, name="Onboarding")
    db_session.add(training)
    await db_session.flush()

    db_session.add(
        EmployeeTraining(tenant_id=1, user_id=user.id, training_id=training.id, status=status)
    )
    await db_session.commit()  # mag niet raisen


@pytest.mark.asyncio
async def test_employee_training_rejects_an_invalid_status(
    db_session: AsyncSession,
) -> None:
    await _make_tenant(db_session, 1, "bad-status")
    user = await _make_user(db_session, 1, "bad-status-user")
    training = Training(tenant_id=1, name="Onboarding")
    db_session.add(training)
    await db_session.flush()

    db_session.add(
        EmployeeTraining(
            tenant_id=1,
            user_id=user.id,
            training_id=training.id,
            status="not_a_real_status",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
