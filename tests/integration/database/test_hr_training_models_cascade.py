"""Cascade-gedrag van `trainings`/`employee_trainings` (BE-AGT-058), bewezen tegen echte Postgres.

SQLite (de unit-testfixture) handhaaft `ondelete=CASCADE`/`SET NULL` alleen met
`PRAGMA foreign_keys=ON`, wat `tests/fixtures/database.py::db_session` niet zet (zelfde
beperking als `tests/unit/test_account_lockout_model.py::test_cascade_delete`). Deze module
bewijst het daadwerkelijke, database-afgedwongen gedrag tegen een echte Postgres via de
`postgres_session`-fixture, die dat probleem niet heeft.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# BEWUST op moduleniveau: `postgres_engine` (tests/fixtures/database.py) importeert een vast
# aantal modellen voordat het `Base.metadata.create_all` aanroept, en `hr_training_models`/
# `hr_skills_models` staan daar niet bij. Zelfde patroon en reden als
# tests/unit/tool_broker/test_hr_skill_gap.py en tests/unit/models/test_hr_training_models.py.
from src.core.models.hr_skills_models import Skill
from src.core.models.hr_training_models import EmployeeTraining, Training
from src.core.models.rbac_models import Tenant, User

pytestmark = [pytest.mark.integration]


def _slug() -> str:
    return uuid.uuid4().hex[:12]


async def _make_tenant(session: AsyncSession) -> Tenant:
    tenant = Tenant(name=f"Tenant {_slug()}", slug=_slug())
    session.add(tenant)
    await session.flush()
    return tenant


async def _make_user(session: AsyncSession, tenant_id: int) -> User:
    user = User(
        tenant_id=tenant_id,
        email=f"{_slug()}@example.test",
        hashed_password="x",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def test_deleting_the_tenant_cascades_trainings_and_employee_trainings(
    postgres_session: AsyncSession,
) -> None:
    tenant = await _make_tenant(postgres_session)
    user = await _make_user(postgres_session, tenant.id)
    training = Training(tenant_id=tenant.id, name=f"Onboarding {_slug()}")
    postgres_session.add(training)
    await postgres_session.flush()
    postgres_session.add(
        EmployeeTraining(tenant_id=tenant.id, user_id=user.id, training_id=training.id)
    )
    await postgres_session.commit()

    await postgres_session.delete(tenant)
    await postgres_session.commit()

    remaining_training = await postgres_session.execute(
        select(Training).where(Training.id == training.id)
    )
    remaining_link = await postgres_session.execute(
        select(EmployeeTraining).where(EmployeeTraining.training_id == training.id)
    )
    assert remaining_training.scalar_one_or_none() is None
    assert remaining_link.scalar_one_or_none() is None


async def test_deleting_the_user_cascades_their_employee_training_rows(
    postgres_session: AsyncSession,
) -> None:
    tenant = await _make_tenant(postgres_session)
    user = await _make_user(postgres_session, tenant.id)
    training = Training(tenant_id=tenant.id, name=f"Onboarding {_slug()}")
    postgres_session.add(training)
    await postgres_session.flush()
    postgres_session.add(
        EmployeeTraining(tenant_id=tenant.id, user_id=user.id, training_id=training.id)
    )
    await postgres_session.commit()

    await postgres_session.delete(user)
    await postgres_session.commit()

    remaining_link = await postgres_session.execute(
        select(EmployeeTraining).where(EmployeeTraining.user_id == user.id)
    )
    remaining_training = await postgres_session.execute(
        select(Training).where(Training.id == training.id)
    )
    assert remaining_link.scalar_one_or_none() is None
    assert remaining_training.scalar_one_or_none() is not None  # de training zelf blijft


async def test_deleting_the_training_cascades_employee_training_rows(
    postgres_session: AsyncSession,
) -> None:
    tenant = await _make_tenant(postgres_session)
    user = await _make_user(postgres_session, tenant.id)
    training = Training(tenant_id=tenant.id, name=f"Onboarding {_slug()}")
    postgres_session.add(training)
    await postgres_session.flush()
    link = EmployeeTraining(tenant_id=tenant.id, user_id=user.id, training_id=training.id)
    postgres_session.add(link)
    await postgres_session.commit()

    await postgres_session.delete(training)
    await postgres_session.commit()

    remaining_link = await postgres_session.execute(
        select(EmployeeTraining).where(EmployeeTraining.id == link.id)
    )
    remaining_user = await postgres_session.execute(select(User).where(User.id == user.id))
    assert remaining_link.scalar_one_or_none() is None
    assert remaining_user.scalar_one_or_none() is not None  # de medewerker zelf blijft


async def test_deleting_the_linked_skill_sets_training_skill_id_to_null(
    postgres_session: AsyncSession,
) -> None:
    tenant = await _make_tenant(postgres_session)
    skill = Skill(tenant_id=tenant.id, name=f"IFRS {_slug()}")
    postgres_session.add(skill)
    await postgres_session.flush()
    training = Training(tenant_id=tenant.id, name=f"IFRS-cert {_slug()}", skill_id=skill.id)
    postgres_session.add(training)
    await postgres_session.commit()

    await postgres_session.delete(skill)
    await postgres_session.commit()
    await postgres_session.refresh(training)

    assert training.skill_id is None  # SET NULL, niet CASCADE: de training zelf blijft bestaan
