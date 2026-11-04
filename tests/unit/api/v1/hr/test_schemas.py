"""`src.core.api.v1.hr.schemas` -- de blank-cel-naar-None/default-normalisatie.

Een aanwezige maar lege CSV-cel parset via `csv.DictReader` tot `""`, niet tot een
ontbrekende sleutel -- zonder normalisatie betekent dat 'moet resolven naar een lege naam' in
plaats van 'geen koppeling bedoeld' (code-review BE-AGT-060 dag 3, finding 6).
"""

from __future__ import annotations

from src.core.api.v1.hr.schemas import (
    EmployeeTrainingImportRowSchema,
    SkillImportRowSchema,
    TrainingImportRowSchema,
)


def test_skill_import_row_schema_treats_a_blank_category_as_none() -> None:
    row = SkillImportRowSchema.model_validate({"name": "Excel", "category": ""})

    assert row.category is None


def test_skill_import_row_schema_keeps_a_real_category_unchanged() -> None:
    row = SkillImportRowSchema.model_validate({"name": "Excel", "category": "office"})

    assert row.category == "office"


def test_skill_import_row_schema_treats_a_missing_category_as_none() -> None:
    row = SkillImportRowSchema.model_validate({"name": "Excel"})

    assert row.category is None


def test_training_import_row_schema_treats_blank_description_and_skill_name_as_none() -> None:
    row = TrainingImportRowSchema.model_validate(
        {"name": "Onboarding", "description": "", "skill_name": ""}
    )

    assert row.description is None
    assert row.skill_name is None


def test_employee_training_import_row_schema_treats_a_blank_status_as_the_default() -> None:
    row = EmployeeTrainingImportRowSchema.model_validate(
        {"user_email": "jan@example.test", "training_name": "Onboarding", "status": ""}
    )

    assert row.status == "assigned"


def test_employee_training_import_row_schema_keeps_a_real_status_unchanged() -> None:
    row = EmployeeTrainingImportRowSchema.model_validate(
        {
            "user_email": "jan@example.test",
            "training_name": "Onboarding",
            "status": "completed",
        }
    )

    assert row.status == "completed"
