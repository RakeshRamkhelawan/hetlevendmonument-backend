"""`HRSkillsImportRepository` (BE-AGT-059, Fase 3 dag 2).

Elke test hier gebruikt een ECHTE database-sessie (SQLite, `db_session`-fixture), niet een
gemockte -- een mock die alleen bevestigt dat `execute()` werd aangeroepen bewijst niets over
tenant-isolatie: hij ziet niet of de WHERE-clausule daadwerkelijk `tenant_id` bevatte. Alleen
een echte query, tegen echte rijen van twee verschillende tenants, kan dat aantonen.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# BEWUST op moduleniveau -- zelfde reden als tests/unit/models/test_hr_training_models.py en
# tests/unit/tool_broker/test_hr_skill_gap.py: de db_session-fixture bouwt het schema via
# Base.metadata.create_all zodra hij voor het eerst gebruikt wordt.
from src.core.models.hr_skills_models import EmployeeSkill, RoleRequiredSkill, Skill
from src.core.models.rbac_models import Role, Tenant, User
from src.core.repositories.hr_import_types import (
    EmployeeAssessmentImportRow,
    RoleRequirementImportRow,
    SkillImportRow,
)
from src.core.repositories.hr_skills_import_repository import HRSkillsImportRepository


async def _make_tenant(session: AsyncSession, tenant_id: int, slug: str) -> Tenant:
    tenant = Tenant(id=tenant_id, name=f"Tenant {slug}", slug=slug)
    session.add(tenant)
    await session.flush()
    return tenant


async def _make_role(session: AsyncSession, tenant_id: int, name: str) -> Role:
    role = Role(tenant_id=tenant_id, name=name)
    session.add(role)
    await session.flush()
    return role


async def _make_user(session: AsyncSession, tenant_id: int, email: str) -> User:
    user = User(tenant_id=tenant_id, email=email, hashed_password="x", is_active=True)
    session.add(user)
    await session.flush()
    return user


# --------------------------------------------------------------------------------------
# upsert_skills
# --------------------------------------------------------------------------------------


async def test_upsert_skills_inserts_new_rows(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "skills-insert")
    repo = HRSkillsImportRepository(db_session)

    outcome = await repo.upsert_skills(
        1, [SkillImportRow(name="Excel"), SkillImportRow(name="IFRS")]
    )

    assert outcome.inserted == 2
    assert outcome.updated == 0
    assert outcome.row_errors == []
    result = await db_session.execute(select(Skill).where(Skill.tenant_id == 1))
    assert {s.name for s in result.scalars().all()} == {"Excel", "IFRS"}


async def test_upsert_skills_updates_an_existing_row_instead_of_duplicating(
    db_session: AsyncSession,
) -> None:
    await _make_tenant(db_session, 1, "skills-update")
    repo = HRSkillsImportRepository(db_session)
    await repo.upsert_skills(1, [SkillImportRow(name="Excel", category="office")])

    outcome = await repo.upsert_skills(1, [SkillImportRow(name="Excel", category="spreadsheet")])

    assert outcome.inserted == 0
    assert outcome.updated == 1
    result = await db_session.execute(select(Skill).where(Skill.tenant_id == 1))
    rows = result.scalars().all()
    assert len(rows) == 1  # geen duplicaat
    assert rows[0].category == "spreadsheet"


async def test_upsert_skills_rejects_an_empty_name_without_aborting_the_batch(
    db_session: AsyncSession,
) -> None:
    await _make_tenant(db_session, 1, "skills-empty-name")
    repo = HRSkillsImportRepository(db_session)

    outcome = await repo.upsert_skills(1, [SkillImportRow(name=""), SkillImportRow(name="Excel")])

    assert outcome.inserted == 1
    assert len(outcome.row_errors) == 1
    assert outcome.row_errors[0].row_index == 1


async def test_upsert_skills_is_tenant_isolated(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "skills-iso-a")
    await _make_tenant(db_session, 2, "skills-iso-b")
    repo = HRSkillsImportRepository(db_session)

    await repo.upsert_skills(1, [SkillImportRow(name="Excel", category="tenant-a")])
    await repo.upsert_skills(2, [SkillImportRow(name="Excel", category="tenant-b")])

    tenant_a_skills = await db_session.execute(select(Skill).where(Skill.tenant_id == 1))
    tenant_b_skills = await db_session.execute(select(Skill).where(Skill.tenant_id == 2))
    assert [s.category for s in tenant_a_skills.scalars().all()] == ["tenant-a"]
    assert [s.category for s in tenant_b_skills.scalars().all()] == ["tenant-b"]


async def test_upsert_skills_handles_the_same_name_appearing_twice_in_one_batch(
    db_session: AsyncSession,
) -> None:
    """De tweede rij moet de eerste in-memory bijwerken, geen dubbele add()/IntegrityError.

    Gevonden door Gate 2 (code-reviewer, 2026-08-22): dit gedrag was al correct geimplementeerd
    maar ongetest -- een toekomstige refactor van de add()-lus zou dit ongemerkt kunnen breken.
    """
    await _make_tenant(db_session, 1, "skills-dup-batch")
    repo = HRSkillsImportRepository(db_session)

    outcome = await repo.upsert_skills(
        1,
        [
            SkillImportRow(name="Excel", category="first"),
            SkillImportRow(name="Excel", category="second"),
        ],
    )

    assert outcome.row_errors == []
    result = await db_session.execute(select(Skill).where(Skill.tenant_id == 1))
    rows = result.scalars().all()
    assert len(rows) == 1  # geen duplicaat, geen IntegrityError
    assert rows[0].category == "second"  # de laatste rij in de batch wint


async def test_upsert_skills_matches_an_existing_row_case_insensitively(
    db_session: AsyncSession,
) -> None:
    """Echte CSV-exports varieren in hoofdlettergebruik (sprint-plan, Ontwerpbeslissing 3) --
    een heruploade 'excel' moet de bestaande 'Excel'-rij bijwerken, geen tweede rij aanmaken."""
    await _make_tenant(db_session, 1, "skills-case-insensitive")
    repo = HRSkillsImportRepository(db_session)
    await repo.upsert_skills(1, [SkillImportRow(name="Excel", category="office")])

    outcome = await repo.upsert_skills(1, [SkillImportRow(name="excel", category="spreadsheet")])

    assert outcome.inserted == 0
    assert outcome.updated == 1
    result = await db_session.execute(select(Skill).where(Skill.tenant_id == 1))
    rows = result.scalars().all()
    assert len(rows) == 1  # geen duplicaat ondanks het hoofdletterverschil
    assert rows[0].category == "spreadsheet"


async def test_upsert_skills_does_not_n_plus_one_the_existing_lookup(
    db_session: AsyncSession,
) -> None:
    """Een gebundelde lookup: 1 SELECT voor de hele batch, niet 1 per rij.

    Telt op DBAPI-niveau via SQLAlchemy's `before_cursor_execute`-event, niet door
    `AsyncSession.execute` te monkeypatchen -- dat laatste heeft geen bruikbare, nauwkeurige
    type-signatuur (elke aanroep-vorm van `execute()` doorgeven zonder `Any` te gebruiken) en
    telt sowieso op het verkeerde niveau: de ORM kan bv. via `flush()` los een INSERT laten
    uitvoeren zonder ooit `AsyncSession.execute()` aan te roepen.
    """
    from sqlalchemy import event

    await _make_tenant(db_session, 1, "skills-n1")
    repo = HRSkillsImportRepository(db_session)

    select_statements: list[str] = []

    def _on_cursor_execute(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        if statement.strip().upper().startswith("SELECT"):
            select_statements.append(statement)

    sync_engine = db_session.bind.sync_engine  # type: ignore[union-attr]
    event.listen(sync_engine, "before_cursor_execute", _on_cursor_execute)
    try:
        rows = [SkillImportRow(name=f"Skill{i}") for i in range(10)]
        await repo.upsert_skills(1, rows)
    finally:
        event.remove(sync_engine, "before_cursor_execute", _on_cursor_execute)

    assert len(select_statements) == 1, (
        f"Verwacht 1 gebundelde SELECT voor de hele batch, kreeg {len(select_statements)}: "
        f"{select_statements}"
    )


# --------------------------------------------------------------------------------------
# upsert_role_requirements
# --------------------------------------------------------------------------------------


async def test_upsert_role_requirements_inserts_new_rows(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "rrs-insert")
    role = await _make_role(db_session, 1, "Accountant")
    repo = HRSkillsImportRepository(db_session)
    await repo.upsert_skills(1, [SkillImportRow(name="IFRS")])

    outcome = await repo.upsert_role_requirements(
        1, [RoleRequirementImportRow(role_name="Accountant", skill_name="IFRS", required_level=4)]
    )

    assert outcome.inserted == 1
    assert outcome.row_errors == []
    result = await db_session.execute(
        select(RoleRequiredSkill).where(RoleRequiredSkill.tenant_id == 1)
    )
    row = result.scalar_one()
    assert row.role_id == role.id
    assert row.required_level == 4


async def test_upsert_role_requirements_updates_the_required_level(
    db_session: AsyncSession,
) -> None:
    await _make_tenant(db_session, 1, "rrs-update")
    await _make_role(db_session, 1, "Accountant")
    repo = HRSkillsImportRepository(db_session)
    await repo.upsert_skills(1, [SkillImportRow(name="IFRS")])
    await repo.upsert_role_requirements(
        1, [RoleRequirementImportRow(role_name="Accountant", skill_name="IFRS", required_level=2)]
    )

    outcome = await repo.upsert_role_requirements(
        1, [RoleRequirementImportRow(role_name="Accountant", skill_name="IFRS", required_level=5)]
    )

    assert outcome.updated == 1
    result = await db_session.execute(
        select(RoleRequiredSkill).where(RoleRequiredSkill.tenant_id == 1)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].required_level == 5


async def test_upsert_role_requirements_rejects_an_unknown_role_name(
    db_session: AsyncSession,
) -> None:
    await _make_tenant(db_session, 1, "rrs-unknown-role")
    repo = HRSkillsImportRepository(db_session)
    await repo.upsert_skills(1, [SkillImportRow(name="IFRS")])

    outcome = await repo.upsert_role_requirements(
        1,
        [RoleRequirementImportRow(role_name="Does Not Exist", skill_name="IFRS", required_level=3)],
    )

    assert outcome.inserted == 0
    assert len(outcome.row_errors) == 1
    assert "Does Not Exist" in outcome.row_errors[0].message


async def test_upsert_role_requirements_rejects_an_unknown_skill_name(
    db_session: AsyncSession,
) -> None:
    await _make_tenant(db_session, 1, "rrs-unknown-skill")
    await _make_role(db_session, 1, "Accountant")
    repo = HRSkillsImportRepository(db_session)

    outcome = await repo.upsert_role_requirements(
        1,
        [RoleRequirementImportRow(role_name="Accountant", skill_name="Nope", required_level=3)],
    )

    assert outcome.inserted == 0
    assert len(outcome.row_errors) == 1


async def test_upsert_role_requirements_rejects_an_out_of_range_level(
    db_session: AsyncSession,
) -> None:
    await _make_tenant(db_session, 1, "rrs-bad-level")
    await _make_role(db_session, 1, "Accountant")
    repo = HRSkillsImportRepository(db_session)
    await repo.upsert_skills(1, [SkillImportRow(name="IFRS")])

    outcome = await repo.upsert_role_requirements(
        1, [RoleRequirementImportRow(role_name="Accountant", skill_name="IFRS", required_level=9)]
    )

    assert outcome.inserted == 0
    assert len(outcome.row_errors) == 1


async def test_upsert_role_requirements_resolves_names_case_insensitively(
    db_session: AsyncSession,
) -> None:
    await _make_tenant(db_session, 1, "rrs-case-insensitive")
    await _make_role(db_session, 1, "Accountant")
    repo = HRSkillsImportRepository(db_session)
    await repo.upsert_skills(1, [SkillImportRow(name="IFRS")])

    outcome = await repo.upsert_role_requirements(
        1, [RoleRequirementImportRow(role_name="accountant", skill_name="ifrs", required_level=4)]
    )

    assert outcome.inserted == 1
    assert outcome.row_errors == []


async def test_upsert_role_requirements_is_tenant_isolated_on_role_name(
    db_session: AsyncSession,
) -> None:
    """Een rol met dezelfde naam in een andere tenant mag NIET resolven."""
    await _make_tenant(db_session, 1, "rrs-iso-a")
    await _make_tenant(db_session, 2, "rrs-iso-b")
    await _make_role(db_session, 2, "Accountant")  # bestaat alleen bij tenant 2
    repo = HRSkillsImportRepository(db_session)
    await repo.upsert_skills(1, [SkillImportRow(name="IFRS")])

    outcome = await repo.upsert_role_requirements(
        1, [RoleRequirementImportRow(role_name="Accountant", skill_name="IFRS", required_level=3)]
    )

    assert outcome.inserted == 0
    assert len(outcome.row_errors) == 1


async def test_upsert_role_requirements_handles_the_same_pair_appearing_twice_in_one_batch(
    db_session: AsyncSession,
) -> None:
    """Zelfde bevinding als bij upsert_skills, maar voor een samengestelde sleutel."""
    await _make_tenant(db_session, 1, "rrs-dup-batch")
    await _make_role(db_session, 1, "Accountant")
    repo = HRSkillsImportRepository(db_session)
    await repo.upsert_skills(1, [SkillImportRow(name="IFRS")])

    outcome = await repo.upsert_role_requirements(
        1,
        [
            RoleRequirementImportRow(role_name="Accountant", skill_name="IFRS", required_level=2),
            RoleRequirementImportRow(role_name="Accountant", skill_name="IFRS", required_level=5),
        ],
    )

    assert outcome.row_errors == []
    result = await db_session.execute(
        select(RoleRequiredSkill).where(RoleRequiredSkill.tenant_id == 1)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].required_level == 5


# --------------------------------------------------------------------------------------
# upsert_employee_assessments
# --------------------------------------------------------------------------------------


async def test_upsert_employee_assessments_inserts_new_rows(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "assess-insert")
    user = await _make_user(db_session, 1, "jan@example.test")
    repo = HRSkillsImportRepository(db_session)
    await repo.upsert_skills(1, [SkillImportRow(name="IFRS")])

    outcome = await repo.upsert_employee_assessments(
        1, [EmployeeAssessmentImportRow(user_email="jan@example.test", skill_name="IFRS", level=3)]
    )

    assert outcome.inserted == 1
    result = await db_session.execute(select(EmployeeSkill).where(EmployeeSkill.tenant_id == 1))
    row = result.scalar_one()
    assert row.user_id == user.id
    assert row.level == 3


async def test_upsert_employee_assessments_updates_the_level(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "assess-update")
    await _make_user(db_session, 1, "jan@example.test")
    repo = HRSkillsImportRepository(db_session)
    await repo.upsert_skills(1, [SkillImportRow(name="IFRS")])
    await repo.upsert_employee_assessments(
        1, [EmployeeAssessmentImportRow(user_email="jan@example.test", skill_name="IFRS", level=2)]
    )

    outcome = await repo.upsert_employee_assessments(
        1, [EmployeeAssessmentImportRow(user_email="jan@example.test", skill_name="IFRS", level=5)]
    )

    assert outcome.updated == 1
    result = await db_session.execute(select(EmployeeSkill).where(EmployeeSkill.tenant_id == 1))
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].level == 5


async def test_upsert_employee_assessments_rejects_an_unknown_email(
    db_session: AsyncSession,
) -> None:
    await _make_tenant(db_session, 1, "assess-unknown-user")
    repo = HRSkillsImportRepository(db_session)
    await repo.upsert_skills(1, [SkillImportRow(name="IFRS")])

    outcome = await repo.upsert_employee_assessments(
        1,
        [EmployeeAssessmentImportRow(user_email="ghost@example.test", skill_name="IFRS", level=3)],
    )

    assert outcome.inserted == 0
    assert len(outcome.row_errors) == 1


async def test_upsert_employee_assessments_treats_a_soft_deleted_user_as_unknown(
    db_session: AsyncSession,
) -> None:
    """Zelfde regel als `query_hr_database`/`analyze_skill_gap`: een gewiste gebruiker telt niet."""
    from datetime import datetime, timezone

    await _make_tenant(db_session, 1, "assess-deleted-user")
    user = await _make_user(db_session, 1, "exemployee@example.test")
    user.deleted_at = datetime.now(timezone.utc)
    await db_session.flush()
    repo = HRSkillsImportRepository(db_session)
    await repo.upsert_skills(1, [SkillImportRow(name="IFRS")])

    outcome = await repo.upsert_employee_assessments(
        1,
        [
            EmployeeAssessmentImportRow(
                user_email="exemployee@example.test", skill_name="IFRS", level=3
            )
        ],
    )

    assert outcome.inserted == 0
    assert len(outcome.row_errors) == 1


async def test_upsert_employee_assessments_resolves_email_and_skill_name_case_insensitively(
    db_session: AsyncSession,
) -> None:
    await _make_tenant(db_session, 1, "assess-case-insensitive")
    await _make_user(db_session, 1, "Jan@Example.test")
    repo = HRSkillsImportRepository(db_session)
    await repo.upsert_skills(1, [SkillImportRow(name="IFRS")])

    outcome = await repo.upsert_employee_assessments(
        1, [EmployeeAssessmentImportRow(user_email="jan@example.TEST", skill_name="ifrs", level=3)]
    )

    assert outcome.inserted == 1
    assert outcome.row_errors == []


async def test_upsert_employee_assessments_is_tenant_isolated_on_email(
    db_session: AsyncSession,
) -> None:
    await _make_tenant(db_session, 1, "assess-iso-a")
    await _make_tenant(db_session, 2, "assess-iso-b")
    await _make_user(db_session, 2, "jan@example.test")  # bestaat alleen bij tenant 2
    repo = HRSkillsImportRepository(db_session)
    await repo.upsert_skills(1, [SkillImportRow(name="IFRS")])

    outcome = await repo.upsert_employee_assessments(
        1, [EmployeeAssessmentImportRow(user_email="jan@example.test", skill_name="IFRS", level=3)]
    )

    assert outcome.inserted == 0
    assert len(outcome.row_errors) == 1


# --------------------------------------------------------------------------------------
# list_skills
# --------------------------------------------------------------------------------------


async def test_list_skills_is_tenant_isolated(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "list-iso-a")
    await _make_tenant(db_session, 2, "list-iso-b")
    repo = HRSkillsImportRepository(db_session)
    await repo.upsert_skills(1, [SkillImportRow(name="TenantA-Skill")])
    await repo.upsert_skills(2, [SkillImportRow(name="TenantB-Skill")])

    tenant_a_result = await repo.list_skills(1)

    assert [s.name for s in tenant_a_result] == ["TenantA-Skill"]


async def test_list_skills_respects_pagination(db_session: AsyncSession) -> None:
    await _make_tenant(db_session, 1, "list-page")
    repo = HRSkillsImportRepository(db_session)
    await repo.upsert_skills(1, [SkillImportRow(name=f"Skill{i}") for i in range(5)])

    page = await repo.list_skills(1, limit=2, offset=1)

    assert len(page) == 2
