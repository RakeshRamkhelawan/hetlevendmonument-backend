"""HRTrainingsRepository -- schrijft de trainings-import-data (BE-AGT-059, Fase 3 dag 2).

Zelfde upsert-semantiek, batching-discipline en "geen automatische Training/User-aanmaak"-
regel als `HRSkillsImportRepository` -- zie die module's docstring voor de volledige
onderbouwing, niet hier herhaald. Idem voor de Python-lengtecontroles hieronder: ze moeten in
sync blijven met `hr_training_models.py`'s kolomdefinities (Gate 2, security-reviewer,
2026-08-22). Idem voor de `func.lower()`-naam-/e-mailmatching hieronder -- zie
`HRSkillsImportRepository`'s docstring voor de ASCII-scope-toelichting.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.hr_skills_models import Skill
from src.core.models.hr_training_models import (
    EMPLOYEE_TRAINING_STATUSES,
    EmployeeTraining,
    Training,
)
from src.core.models.rbac_models import User
from src.core.repositories.hr_import_types import (
    EmployeeTrainingImportRow,
    ImportRowError,
    TrainingImportRow,
    UpsertOutcome,
)

#: Moet gelijk blijven aan Training.name/`String(150)` (hr_training_models.py).
TRAINING_NAME_MAX_LENGTH = 150
#: Moet gelijk blijven aan Training.description/`String(500)` (hr_training_models.py).
TRAINING_DESCRIPTION_MAX_LENGTH = 500


class HRTrainingsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def upsert_trainings(
        self, tenant_id: int, rows: list[TrainingImportRow]
    ) -> UpsertOutcome:
        if not rows:
            return UpsertOutcome(inserted=0, updated=0, row_errors=[])

        names = [row.name for row in rows]
        skill_names = {row.skill_name for row in rows if row.skill_name is not None}
        existing_result = await self.db.execute(
            select(Training).where(
                Training.tenant_id == tenant_id,
                func.lower(Training.name).in_([n.lower() for n in names]),
            )
        )
        existing_by_name = {
            training.name.lower(): training for training in existing_result.scalars().all()
        }
        skills_by_name: dict[str, Skill] = {}
        if skill_names:
            skills_result = await self.db.execute(
                select(Skill).where(
                    Skill.tenant_id == tenant_id,
                    func.lower(Skill.name).in_([n.lower() for n in skill_names]),
                )
            )
            skills_by_name = {skill.name.lower(): skill for skill in skills_result.scalars().all()}

        inserted = 0
        updated = 0
        row_errors: list[ImportRowError] = []
        for index, row in enumerate(rows, start=1):
            if not row.name or not row.name.strip():
                row_errors.append(ImportRowError(row_index=index, message="name is verplicht"))
                continue
            if len(row.name) > TRAINING_NAME_MAX_LENGTH:
                row_errors.append(
                    ImportRowError(
                        row_index=index,
                        message=f"name mag maximaal {TRAINING_NAME_MAX_LENGTH} tekens zijn",
                    )
                )
                continue
            if (
                row.description is not None
                and len(row.description) > TRAINING_DESCRIPTION_MAX_LENGTH
            ):
                row_errors.append(
                    ImportRowError(
                        row_index=index,
                        message=(
                            f"description mag maximaal {TRAINING_DESCRIPTION_MAX_LENGTH} "
                            "tekens zijn"
                        ),
                    )
                )
                continue

            skill_id: int | None = None
            if row.skill_name is not None:
                skill = skills_by_name.get(row.skill_name.lower())
                if skill is None:
                    row_errors.append(
                        ImportRowError(
                            row_index=index, message=f"onbekende vaardigheid: {row.skill_name}"
                        )
                    )
                    continue
                skill_id = skill.id

            existing = existing_by_name.get(row.name.lower())
            if existing is not None:
                existing.description = row.description
                existing.skill_id = skill_id
                updated += 1
            else:
                new_training = Training(
                    tenant_id=tenant_id,
                    name=row.name,
                    description=row.description,
                    skill_id=skill_id,
                )
                self.db.add(new_training)
                existing_by_name[row.name.lower()] = new_training
                inserted += 1

        await self.db.flush()
        return UpsertOutcome(inserted=inserted, updated=updated, row_errors=row_errors)

    async def upsert_employee_trainings(
        self, tenant_id: int, rows: list[EmployeeTrainingImportRow]
    ) -> UpsertOutcome:
        if not rows:
            return UpsertOutcome(inserted=0, updated=0, row_errors=[])

        user_emails = {row.user_email for row in rows}
        training_names = {row.training_name for row in rows}
        users_result = await self.db.execute(
            select(User).where(
                User.tenant_id == tenant_id,
                func.lower(User.email).in_([e.lower() for e in user_emails]),
                User.deleted_at.is_(None),
            )
        )
        users_by_email = {user.email.lower(): user for user in users_result.scalars().all()}
        trainings_result = await self.db.execute(
            select(Training).where(
                Training.tenant_id == tenant_id,
                func.lower(Training.name).in_([n.lower() for n in training_names]),
            )
        )
        trainings_by_name = {
            training.name.lower(): training for training in trainings_result.scalars().all()
        }
        # Gescoopt op de gebruiker-/training-ids die deze batch raakt, niet de hele
        # tenant-tabel -- zelfde reden als HRSkillsImportRepository's composite-key-lookups
        # (Gate 2, code+security-reviewer, 2026-08-22).
        user_ids = [user.id for user in users_by_email.values()]
        training_ids = [training.id for training in trainings_by_name.values()]
        existing_by_key: dict[tuple[int, int], EmployeeTraining] = {}
        if user_ids and training_ids:
            existing_result = await self.db.execute(
                select(EmployeeTraining).where(
                    EmployeeTraining.tenant_id == tenant_id,
                    EmployeeTraining.user_id.in_(user_ids),
                    EmployeeTraining.training_id.in_(training_ids),
                )
            )
            existing_by_key = {
                (row.user_id, row.training_id): row for row in existing_result.scalars().all()
            }

        inserted = 0
        updated = 0
        row_errors: list[ImportRowError] = []
        for index, row in enumerate(rows, start=1):
            user = users_by_email.get(row.user_email.lower())
            training = trainings_by_name.get(row.training_name.lower())
            if user is None:
                # Geen e-mailadres in de message -- PII, en row_index identificeert de rij al
                # (zelfde OP-27-redenering als de audit-log in trainings_import_router.py).
                row_errors.append(ImportRowError(row_index=index, message="onbekende gebruiker"))
                continue
            if training is None:
                row_errors.append(
                    ImportRowError(
                        row_index=index, message=f"onbekende training: {row.training_name}"
                    )
                )
                continue
            if row.status not in EMPLOYEE_TRAINING_STATUSES:
                row_errors.append(
                    ImportRowError(
                        row_index=index,
                        message=(
                            f"status moet een van {EMPLOYEE_TRAINING_STATUSES} zijn, kreeg "
                            f"{row.status!r}"
                        ),
                    )
                )
                continue

            key = (user.id, training.id)
            existing = existing_by_key.get(key)
            if existing is not None:
                existing.status = row.status
                updated += 1
            else:
                new_row = EmployeeTraining(
                    tenant_id=tenant_id,
                    user_id=user.id,
                    training_id=training.id,
                    status=row.status,
                )
                self.db.add(new_row)
                existing_by_key[key] = new_row
                inserted += 1

        await self.db.flush()
        return UpsertOutcome(inserted=inserted, updated=updated, row_errors=row_errors)

    async def list_trainings(
        self, tenant_id: int, limit: int = 50, offset: int = 0
    ) -> list[Training]:
        # Zelfde klem als HRSkillsImportRepository.list_skills -- niet louter op de
        # Dag-3-API-laag vertrouwen.
        clamped_limit = min(limit, 1000)
        result = await self.db.execute(
            select(Training)
            .where(Training.tenant_id == tenant_id)
            .order_by(Training.name)
            .limit(clamped_limit)
            .offset(offset)
        )
        return list(result.scalars().all())
