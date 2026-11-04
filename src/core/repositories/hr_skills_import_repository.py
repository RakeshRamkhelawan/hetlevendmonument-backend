"""HRSkillsImportRepository -- schrijft de skills-import-data (BE-AGT-059, Fase 3 dag 2).

Upsert, geen reject-on-duplicate: een tenant-admin die een gecorrigeerd bestand herupload
mag niet op een aparte PATCH-route stuiten. Elke methode doet EEN gebundelde SELECT voor de
hele batch (geen N+1 per rij, bewaakt door `tests/unit/repositories/
test_hr_skills_import_repository.py::test_upsert_skills_does_not_n_plus_one_the_existing_
lookup`), dan `add()` voor nieuw / attribuutwijziging voor bestaand, een `flush()` aan het
einde.

**Waarom Python-niveau validatie VOOR `add()`, niet alleen de DB-CHECK-constraint erop laten
afvangen.** Een CHECK-constraint-schending tijdens `flush()` gooit een `IntegrityError` die de
HELE batch treft (of op zijn minst de rest van diezelfde flush), niet alleen de foute rij --
dat zou het "per-rij-fout, batch gaat door"-contract breken. Elke voorwaarde die de database
zelf ook afdwingt (niveau-bereik, status-vocabulaire) wordt daarom hier al gecontroleerd,
VOORDAT de rij aan de sessie wordt toegevoegd.

**Waarom geen automatische aanmaak van `Role`/`User`.** Een rij die naar een onbestaande rol
of gebruiker verwijst wordt afgewezen, nooit stilzwijgend aangemaakt -- rol- en
gebruikersaanmaak hebben al hun eigen onboarding/RBAC-pad; dit import-pad mag daar geen
schaduwpad naast worden.

**Waarom een Python-lengtecontrole naast de DB-`VARCHAR`-grens.** Zelfde reden als de
niveau-/statuscontroles hierboven: SQLite (de unit-testfixture) handhaaft `VARCHAR(n)` niet,
dus een te lange waarde zou hier ongezien groen blijven en pas bij een echte Postgres een
onopgevangen `DataError` gooien die de HELE batch treft (Gate 2, security-reviewer,
2026-08-22). De grenzen hieronder MOETEN in sync blijven met `hr_skills_models.py`'s
kolomdefinities -- ze zijn geen eigen, onafhankelijke waarheid.

**Waarom `func.lower()` voor naam-/e-mailmatching (niet `.in_()` op de ruwe waarde).** Het
sprint-plan eist expliciet case-insensitieve naam-matching (echte CSV-exports varieren in
hoofdlettergebruik) -- ontbrak aanvankelijk volledig, gevonden door Gate 2 code-review,
2026-08-22. `func.lower()` dekt ASCII correct op zowel SQLite (testfixture) als Postgres
(productie); niet-ASCII hoofdletter-varianten (bv. een naam met een accent) vallen hierbuiten
omdat SQLite's ingebouwde `LOWER()` alleen ASCII casefold, tenzij de ICU-extensie geladen is --
Postgres doet dat wel. Dat is een bestaande, gedocumenteerde SQLite-beperking (zie de
lengtecontrole hierboven voor hetzelfde patroon), geen nieuwe aanname; de namen in deze
catalogus zijn in de praktijk overwegend ASCII (skill-/rol-/trainingsnamen). De uiteindelijke
match-beslissing gebeurt in Python via `.lower()` op de dict-sleutel -- de SQL-kant is alleen
een grove voorfilter om niet de hele tenant-tabel te laden.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.hr_skills_models import (
    MAX_SKILL_LEVEL,
    MIN_SKILL_LEVEL,
    EmployeeSkill,
    RoleRequiredSkill,
    Skill,
)
from src.core.models.rbac_models import Role, User
from src.core.repositories.hr_import_types import (
    EmployeeAssessmentImportRow,
    ImportRowError,
    RoleRequirementImportRow,
    SkillImportRow,
    UpsertOutcome,
)

#: Moet gelijk blijven aan Skill.name/`String(100)` (hr_skills_models.py).
SKILL_NAME_MAX_LENGTH = 100
#: Moet gelijk blijven aan Skill.category/`String(50)` (hr_skills_models.py).
SKILL_CATEGORY_MAX_LENGTH = 50


class HRSkillsImportRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def upsert_skills(self, tenant_id: int, rows: list[SkillImportRow]) -> UpsertOutcome:
        if not rows:
            return UpsertOutcome(inserted=0, updated=0, row_errors=[])

        names = [row.name for row in rows]
        existing_result = await self.db.execute(
            select(Skill).where(
                Skill.tenant_id == tenant_id, func.lower(Skill.name).in_([n.lower() for n in names])
            )
        )
        existing_by_name = {skill.name.lower(): skill for skill in existing_result.scalars().all()}

        inserted = 0
        updated = 0
        row_errors: list[ImportRowError] = []
        for index, row in enumerate(rows, start=1):
            if not row.name or not row.name.strip():
                row_errors.append(ImportRowError(row_index=index, message="name is verplicht"))
                continue
            if len(row.name) > SKILL_NAME_MAX_LENGTH:
                row_errors.append(
                    ImportRowError(
                        row_index=index,
                        message=f"name mag maximaal {SKILL_NAME_MAX_LENGTH} tekens zijn",
                    )
                )
                continue
            if row.category is not None and len(row.category) > SKILL_CATEGORY_MAX_LENGTH:
                row_errors.append(
                    ImportRowError(
                        row_index=index,
                        message=f"category mag maximaal {SKILL_CATEGORY_MAX_LENGTH} tekens zijn",
                    )
                )
                continue
            existing = existing_by_name.get(row.name.lower())
            if existing is not None:
                existing.category = row.category
                updated += 1
            else:
                new_skill = Skill(tenant_id=tenant_id, name=row.name, category=row.category)
                self.db.add(new_skill)
                existing_by_name[row.name.lower()] = new_skill
                inserted += 1

        await self.db.flush()
        return UpsertOutcome(inserted=inserted, updated=updated, row_errors=row_errors)

    async def upsert_role_requirements(
        self, tenant_id: int, rows: list[RoleRequirementImportRow]
    ) -> UpsertOutcome:
        if not rows:
            return UpsertOutcome(inserted=0, updated=0, row_errors=[])

        role_names = {row.role_name for row in rows}
        skill_names = {row.skill_name for row in rows}
        roles_result = await self.db.execute(
            select(Role).where(
                Role.tenant_id == tenant_id,
                func.lower(Role.name).in_([n.lower() for n in role_names]),
            )
        )
        roles_by_name = {role.name.lower(): role for role in roles_result.scalars().all()}
        skills_result = await self.db.execute(
            select(Skill).where(
                Skill.tenant_id == tenant_id,
                func.lower(Skill.name).in_([n.lower() for n in skill_names]),
            )
        )
        skills_by_name = {skill.name.lower(): skill for skill in skills_result.scalars().all()}
        # Gescoopt op de rol-/skill-ids die deze batch daadwerkelijk raakt, niet de hele
        # tenant-tabel -- anders schaalt deze lookup met de historische omvang van de tenant
        # in plaats van met de batchgrootte (Gate 2, code+security-reviewer, 2026-08-22).
        role_ids = [role.id for role in roles_by_name.values()]
        skill_ids = [skill.id for skill in skills_by_name.values()]
        existing_by_key: dict[tuple[int, int], RoleRequiredSkill] = {}
        if role_ids and skill_ids:
            existing_result = await self.db.execute(
                select(RoleRequiredSkill).where(
                    RoleRequiredSkill.tenant_id == tenant_id,
                    RoleRequiredSkill.role_id.in_(role_ids),
                    RoleRequiredSkill.skill_id.in_(skill_ids),
                )
            )
            existing_by_key = {
                (row.role_id, row.skill_id): row for row in existing_result.scalars().all()
            }

        inserted = 0
        updated = 0
        row_errors: list[ImportRowError] = []
        for index, row in enumerate(rows, start=1):
            role = roles_by_name.get(row.role_name.lower())
            skill = skills_by_name.get(row.skill_name.lower())
            if role is None:
                row_errors.append(
                    ImportRowError(row_index=index, message=f"onbekende rol: {row.role_name}")
                )
                continue
            if skill is None:
                row_errors.append(
                    ImportRowError(
                        row_index=index, message=f"onbekende vaardigheid: {row.skill_name}"
                    )
                )
                continue
            if not (MIN_SKILL_LEVEL <= row.required_level <= MAX_SKILL_LEVEL):
                row_errors.append(
                    ImportRowError(
                        row_index=index,
                        message=(
                            f"required_level moet tussen {MIN_SKILL_LEVEL} en "
                            f"{MAX_SKILL_LEVEL} liggen, kreeg {row.required_level}"
                        ),
                    )
                )
                continue

            key = (role.id, skill.id)
            existing = existing_by_key.get(key)
            if existing is not None:
                existing.required_level = row.required_level
                updated += 1
            else:
                new_row = RoleRequiredSkill(
                    tenant_id=tenant_id,
                    role_id=role.id,
                    skill_id=skill.id,
                    required_level=row.required_level,
                )
                self.db.add(new_row)
                existing_by_key[key] = new_row
                inserted += 1

        await self.db.flush()
        return UpsertOutcome(inserted=inserted, updated=updated, row_errors=row_errors)

    async def upsert_employee_assessments(
        self, tenant_id: int, rows: list[EmployeeAssessmentImportRow]
    ) -> UpsertOutcome:
        if not rows:
            return UpsertOutcome(inserted=0, updated=0, row_errors=[])

        user_emails = {row.user_email for row in rows}
        skill_names = {row.skill_name for row in rows}
        users_result = await self.db.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                func.lower(User.email).in_([e.lower() for e in user_emails]),
                User.deleted_at.is_(None),
            )
        )
        users_by_email = {user.email.lower(): user for user in users_result.scalars().all()}
        skills_result = await self.db.execute(
            select(Skill).where(
                Skill.tenant_id == tenant_id,
                func.lower(Skill.name).in_([n.lower() for n in skill_names]),
            )
        )
        skills_by_name = {skill.name.lower(): skill for skill in skills_result.scalars().all()}
        # Gescoopt op de gebruiker-/skill-ids die deze batch raakt -- zelfde reden als
        # upsert_role_requirements hierboven.
        user_ids = [user.id for user in users_by_email.values()]
        skill_ids = [skill.id for skill in skills_by_name.values()]
        existing_by_key: dict[tuple[int, int], EmployeeSkill] = {}
        if user_ids and skill_ids:
            existing_result = await self.db.execute(
                select(EmployeeSkill).where(
                    EmployeeSkill.tenant_id == tenant_id,
                    EmployeeSkill.user_id.in_(user_ids),
                    EmployeeSkill.skill_id.in_(skill_ids),
                )
            )
            existing_by_key = {
                (row.user_id, row.skill_id): row for row in existing_result.scalars().all()
            }

        inserted = 0
        updated = 0
        row_errors: list[ImportRowError] = []
        for index, row in enumerate(rows, start=1):
            user = users_by_email.get(row.user_email.lower())
            skill = skills_by_name.get(row.skill_name.lower())
            if user is None:
                # Geen e-mailadres in de message -- PII, en row_index identificeert de rij al
                # (zelfde OP-27-redenering als de audit-log in skills_import_router.py).
                row_errors.append(ImportRowError(row_index=index, message="onbekende gebruiker"))
                continue
            if skill is None:
                row_errors.append(
                    ImportRowError(
                        row_index=index, message=f"onbekende vaardigheid: {row.skill_name}"
                    )
                )
                continue
            if not (MIN_SKILL_LEVEL <= row.level <= MAX_SKILL_LEVEL):
                row_errors.append(
                    ImportRowError(
                        row_index=index,
                        message=(
                            f"level moet tussen {MIN_SKILL_LEVEL} en {MAX_SKILL_LEVEL} liggen, "
                            f"kreeg {row.level}"
                        ),
                    )
                )
                continue

            key = (user.id, skill.id)
            existing = existing_by_key.get(key)
            if existing is not None:
                existing.level = row.level
                updated += 1
            else:
                new_row = EmployeeSkill(
                    tenant_id=tenant_id,
                    user_id=user.id,
                    skill_id=skill.id,
                    level=row.level,
                )
                self.db.add(new_row)
                existing_by_key[key] = new_row
                inserted += 1

        await self.db.flush()
        return UpsertOutcome(inserted=inserted, updated=updated, row_errors=row_errors)

    async def list_skills(self, tenant_id: int, limit: int = 50, offset: int = 0) -> list[Skill]:
        # Geklemd op 1000, ook al is de Dag-3-API-laag zelf al `Query(le=1000)` -- deze
        # methode moet niet louter op die buitenste laag vertrouwen (Gate 2, security-
        # reviewer, 2026-08-22).
        clamped_limit = min(limit, 1000)
        result = await self.db.execute(
            select(Skill)
            .where(Skill.tenant_id == tenant_id)
            .order_by(Skill.name)
            .limit(clamped_limit)
            .offset(offset)
        )
        return list(result.scalars().all())
