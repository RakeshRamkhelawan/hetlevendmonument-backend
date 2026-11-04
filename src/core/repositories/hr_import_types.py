"""Rijtypen voor de HR-data-import (BE-AGT-059, Fase 3 dag 2, vervolg op BE-AGT-058).

Bewust hier, op de repository-laag, en niet in `src/core/api/v1/hr/schemas.py` (dag 3): de
repository-laag mag niet afhangen van de API-laag (ADR-033-richting is andersom). Dag 3's
Pydantic-schemas valideren/parseren het ruwe CSV/JSON-bestand en bouwen daarna deze
dataclasses; de repository-laag kent Pydantic niet en hoeft het niet te kennen.

`row_index` in `ImportRowError` is 1-based over de `rows`-lijst die de repository binnenkrijgt
(de eerste rij is 1) -- NIET header-inclusief. De API-laag (dag 3), die het ruwe bestand met
zijn headerregel kent, mag dat cijfer omrekenen naar wat een gebruiker in een spreadsheet ziet;
de repository kent geen headerregel en moet dat onderscheid niet verzinnen.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SkillImportRow:
    name: str
    category: str | None = None


@dataclass(frozen=True)
class RoleRequirementImportRow:
    role_name: str
    skill_name: str
    required_level: int


@dataclass(frozen=True)
class EmployeeAssessmentImportRow:
    user_email: str
    skill_name: str
    level: int


@dataclass(frozen=True)
class TrainingImportRow:
    name: str
    description: str | None = None
    skill_name: str | None = None


@dataclass(frozen=True)
class EmployeeTrainingImportRow:
    user_email: str
    training_name: str
    status: str = "assigned"


@dataclass(frozen=True)
class ImportRowError:
    row_index: int
    message: str


@dataclass(frozen=True)
class UpsertOutcome:
    inserted: int
    updated: int
    row_errors: list[ImportRowError] = field(default_factory=list)
