"""`HRTrainingsRepository` (BE-AGT-059, Fase 3 dag 2).

Zelfde discipline als `test_hr_skills_import_repository.py`: echte database-sessie, geen
mocks -- alleen een echte query tegen rijen van twee tenants bewijst tenant-isolatie.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# BEWUST op moduleniveau -- zelfde reden als de andere HR-testbestanden.
from src.core.models.hr_skills_models import Skill
from src.core.models.hr_training_models import EmployeeTraining, Training
from src.core.models.rbac_models import Tenant, User
from src.core.repositories.hr_import_types import (
    EmployeeTrainingImportRow,
    TrainingImportRow,
)
from src.core.repositories.hr_trainings_repository import HRTrainingsRepository


async def _make_tenant(session: AsyncSession, tenant_id: int, slug: str) -> Tenant:
    tenant = Tenant(id=tenant_id, name=f"Tenant {slug}", slug=slug)
    session.add(tenant)
    await session.flush()
    return tenant


async def _make_user(session: AsyncSession, tenant_id: int, email: str) -> User:
    user = User(tenant_id=tenant_id, email=email, hashed_password="x", is_active=True)
    session.add(user)
    await session.flush()
    return user


# --------------------------------------------------------------------------------------
# upsert_trainings
# --------------------------------------------------------------------------------------


async def test_upsert_trainings_inserts_new_rows(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "trn-insert")
    repo = HRTrainingsRepository(db_session)

    outcome = await repo.upsert_trainings(
        1, [TrainingImportRow(name="Onboarding"), TrainingImportRow(name="IFRS-cert")]
    )

    assert outcome.inserted == 2
    assert outcome.row_errors == []
    result = await db_session.execute(select(Training).where(Training.tenant_id == 1))
    assert {t.name for t in result.scalars().all()} == {"Onboarding", "IFRS-cert"}


async def test_upsert_trainings_updates_the_description(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "trn-update")
    repo = HRTrainingsRepository(db_session)
    await repo.upsert_trainings(1, [TrainingImportRow(name="Onboarding", description="v1")])

    outcome = await repo.upsert_trainings(
        1, [TrainingImportRow(name="Onboarding", description="v2")]
    )

    assert outcome.updated == 1
    result = await db_session.execute(select(Training).where(Training.tenant_id == 1))
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].description == "v2"


async def test_upsert_trainings_matches_an_existing_row_case_insensitively(
    db_session: AsyncSession,
) -> None:
    """Zelfde bevinding als `test_hr_skills_import_repository.py`'s equivalent -- de
    sprint-plan-eis 'CASE-INSENSITIVE' geldt voor elke naam-matching, niet alleen skills."""
    await _make_tenant(db_session, 1, "trn-case-insensitive")
    repo = HRTrainingsRepository(db_session)
    await repo.upsert_trainings(1, [TrainingImportRow(name="Onboarding", description="v1")])

    outcome = await repo.upsert_trainings(
        1, [TrainingImportRow(name="onboarding", description="v2")]
    )

    assert outcome.inserted == 0
    assert outcome.updated == 1
    result = await db_session.execute(select(Training).where(Training.tenant_id == 1))
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].description == "v2"


async def test_upsert_trainings_links_a_known_skill_by_name(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "trn-skill-link")
    skill = Skill(tenant_id=1, name="IFRS")
    db_session.add(skill)
    await db_session.flush()
    repo = HRTrainingsRepository(db_session)

    outcome = await repo.upsert_trainings(
        1, [TrainingImportRow(name="IFRS-cert", skill_name="IFRS")]
    )

    assert outcome.inserted == 1
    result = await db_session.execute(select(Training).where(Training.tenant_id == 1))
    row = result.scalar_one()
    assert row.skill_id == skill.id


async def test_upsert_trainings_rejects_an_unknown_skill_name(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "trn-unknown-skill")
    repo = HRTrainingsRepository(db_session)

    outcome = await repo.upsert_trainings(
        1, [TrainingImportRow(name="IFRS-cert", skill_name="Does Not Exist")]
    )

    assert outcome.inserted == 0
    assert len(outcome.row_errors) == 1


async def test_upsert_trainings_is_tenant_isolated(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "trn-iso-a")
    await _make_tenant(db_session, 2, "trn-iso-b")
    repo = HRTrainingsRepository(db_session)

    await repo.upsert_trainings(1, [TrainingImportRow(name="Onboarding", description="a")])
    await repo.upsert_trainings(2, [TrainingImportRow(name="Onboarding", description="b")])

    tenant_a = await db_session.execute(select(Training).where(Training.tenant_id == 1))
    tenant_b = await db_session.execute(select(Training).where(Training.tenant_id == 2))
    assert [t.description for t in tenant_a.scalars().all()] == ["a"]
    assert [t.description for t in tenant_b.scalars().all()] == ["b"]


# --------------------------------------------------------------------------------------
# upsert_employee_trainings
# --------------------------------------------------------------------------------------


async def test_upsert_employee_trainings_inserts_new_rows(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "et-insert")
    user = await _make_user(db_session, 1, "jan@example.test")
    repo = HRTrainingsRepository(db_session)
    await repo.upsert_trainings(1, [TrainingImportRow(name="Onboarding")])

    outcome = await repo.upsert_employee_trainings(
        1, [EmployeeTrainingImportRow(user_email="jan@example.test", training_name="Onboarding")]
    )

    assert outcome.inserted == 1
    result = await db_session.execute(
        select(EmployeeTraining).where(EmployeeTraining.tenant_id == 1)
    )
    row = result.scalar_one()
    assert row.user_id == user.id
    assert row.status == "assigned"


async def test_upsert_employee_trainings_resolves_email_and_training_name_case_insensitively(
    db_session: AsyncSession,
) -> None:
    await _make_tenant(db_session, 1, "et-case-insensitive")
    await _make_user(db_session, 1, "Jan@Example.test")
    repo = HRTrainingsRepository(db_session)
    await repo.upsert_trainings(1, [TrainingImportRow(name="Onboarding")])

    outcome = await repo.upsert_employee_trainings(
        1,
        [EmployeeTrainingImportRow(user_email="jan@example.TEST", training_name="onboarding")],
    )

    assert outcome.inserted == 1
    assert outcome.row_errors == []


async def test_upsert_employee_trainings_updates_the_status(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "et-update")
    await _make_user(db_session, 1, "jan@example.test")
    repo = HRTrainingsRepository(db_session)
    await repo.upsert_trainings(1, [TrainingImportRow(name="Onboarding")])
    await repo.upsert_employee_trainings(
        1, [EmployeeTrainingImportRow(user_email="jan@example.test", training_name="Onboarding")]
    )

    outcome = await repo.upsert_employee_trainings(
        1,
        [
            EmployeeTrainingImportRow(
                user_email="jan@example.test", training_name="Onboarding", status="completed"
            )
        ],
    )

    assert outcome.updated == 1
    result = await db_session.execute(
        select(EmployeeTraining).where(EmployeeTraining.tenant_id == 1)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "completed"


async def test_upsert_employee_trainings_rejects_an_invalid_status(
    db_session: AsyncSession,
) -> None:
    await _make_tenant(db_session, 1, "et-bad-status")
    await _make_user(db_session, 1, "jan@example.test")
    repo = HRTrainingsRepository(db_session)
    await repo.upsert_trainings(1, [TrainingImportRow(name="Onboarding")])

    outcome = await repo.upsert_employee_trainings(
        1,
        [
            EmployeeTrainingImportRow(
                user_email="jan@example.test",
                training_name="Onboarding",
                status="not_a_real_status",
            )
        ],
    )

    assert outcome.inserted == 0
    assert len(outcome.row_errors) == 1


async def test_upsert_employee_trainings_rejects_an_unknown_training_name(
    db_session: AsyncSession,
) -> None:
    await _make_tenant(db_session, 1, "et-unknown-training")
    await _make_user(db_session, 1, "jan@example.test")
    repo = HRTrainingsRepository(db_session)

    outcome = await repo.upsert_employee_trainings(
        1, [EmployeeTrainingImportRow(user_email="jan@example.test", training_name="Nope")]
    )

    assert outcome.inserted == 0
    assert len(outcome.row_errors) == 1


async def test_upsert_employee_trainings_rejects_an_unknown_email(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "et-unknown-user")
    repo = HRTrainingsRepository(db_session)
    await repo.upsert_trainings(1, [TrainingImportRow(name="Onboarding")])

    outcome = await repo.upsert_employee_trainings(
        1, [EmployeeTrainingImportRow(user_email="ghost@example.test", training_name="Onboarding")]
    )

    assert outcome.inserted == 0
    assert len(outcome.row_errors) == 1


async def test_upsert_employee_trainings_is_tenant_isolated_on_training_name(
    db_session: AsyncSession,
) -> None:
    """Een training met dezelfde naam in een andere tenant mag NIET resolven."""
    await _make_tenant(db_session, 1, "et-iso-a")
    await _make_tenant(db_session, 2, "et-iso-b")
    await _make_user(db_session, 1, "jan@example.test")
    repo = HRTrainingsRepository(db_session)
    await repo.upsert_trainings(2, [TrainingImportRow(name="Onboarding")])  # alleen bij tenant 2

    outcome = await repo.upsert_employee_trainings(
        1, [EmployeeTrainingImportRow(user_email="jan@example.test", training_name="Onboarding")]
    )

    assert outcome.inserted == 0
    assert len(outcome.row_errors) == 1


async def test_upsert_employee_trainings_treats_a_soft_deleted_user_as_unknown(
    db_session: AsyncSession,
) -> None:
    """Symmetrie met de skills-repository's zelfde regel (Gate 2, security-reviewer,
    2026-08-22): een medewerker in de AVG-wisroute mag geen nieuwe trainingsdata krijgen."""
    from datetime import datetime, timezone

    await _make_tenant(db_session, 1, "et-deleted-user")
    user = await _make_user(db_session, 1, "exemployee@example.test")
    user.deleted_at = datetime.now(timezone.utc)
    await db_session.flush()
    repo = HRTrainingsRepository(db_session)
    await repo.upsert_trainings(1, [TrainingImportRow(name="Onboarding")])

    outcome = await repo.upsert_employee_trainings(
        1,
        [
            EmployeeTrainingImportRow(
                user_email="exemployee@example.test", training_name="Onboarding"
            )
        ],
    )

    assert outcome.inserted == 0
    assert len(outcome.row_errors) == 1


async def test_upsert_employee_trainings_handles_the_same_pair_appearing_twice_in_one_batch(
    db_session: AsyncSession,
) -> None:
    await _make_tenant(db_session, 1, "et-dup-batch")
    await _make_user(db_session, 1, "jan@example.test")
    repo = HRTrainingsRepository(db_session)
    await repo.upsert_trainings(1, [TrainingImportRow(name="Onboarding")])

    outcome = await repo.upsert_employee_trainings(
        1,
        [
            EmployeeTrainingImportRow(user_email="jan@example.test", training_name="Onboarding"),
            EmployeeTrainingImportRow(
                user_email="jan@example.test", training_name="Onboarding", status="completed"
            ),
        ],
    )

    assert outcome.row_errors == []
    result = await db_session.execute(
        select(EmployeeTraining).where(EmployeeTraining.tenant_id == 1)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "completed"


# --------------------------------------------------------------------------------------
# list_trainings
# --------------------------------------------------------------------------------------


async def test_list_trainings_is_tenant_isolated(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "list-trn-iso-a")
    await _make_tenant(db_session, 2, "list-trn-iso-b")
    repo = HRTrainingsRepository(db_session)
    await repo.upsert_trainings(1, [TrainingImportRow(name="TenantA-Training")])
    await repo.upsert_trainings(2, [TrainingImportRow(name="TenantB-Training")])

    tenant_a_result = await repo.list_trainings(1)

    assert [t.name for t in tenant_a_result] == ["TenantA-Training"]


async def test_list_trainings_respects_pagination(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "list-trn-page")
    repo = HRTrainingsRepository(db_session)
    await repo.upsert_trainings(1, [TrainingImportRow(name=f"Training{i}") for i in range(5)])

    page = await repo.list_trainings(1, limit=2, offset=1)

    assert len(page) == 2
