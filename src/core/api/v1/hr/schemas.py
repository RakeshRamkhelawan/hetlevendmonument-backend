"""Pydantic-schemas voor het `hr`-import-domein (BE-AGT-060, Fase 3 dag 3).

Elke schema hier valideert/type-coerceert EEN rij uit een ruw CSV/JSON-bestand (bv.
`required_level` komt uit CSV als tekst en moet een `int` worden). Na validatie bouwt de
router er een dataclass uit `src.core.repositories.hr_import_types` van -- de repository-laag
kent Pydantic niet (ADR-033-richting: API hangt af van data, niet omgekeerd).

`MAX_IMPORT_ROWS`: een batch van 0 of > 500 rijen wordt in zijn geheel afgewezen (400), NOOIT
stilzwijgend afgekapt -- een afkapping op een SCHRIJF-actie zou de aanvrager niet laten weten
welke rijen nooit zijn verwerkt. Dit wijkt bewust af van `hr_registry.py`'s leespad, dat wel
afkapt (`applied_limit`) -- dat is veilig voor een LEZING, niet voor een schrijfactie.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_IMPORT_ROWS = 500


def _blank_to_none(value: object) -> object:
    """Een CSV-cel die aanwezig maar leeg is parset tot `""`, niet tot een ontbrekende kolom
    (die wordt al wel Pydantic's eigen default) -- zonder deze normalisatie betekent een lege
    cel op een optioneel veld 'moet resolven naar een lege naam', niet 'geen koppeling
    bedoeld' (code-review BE-AGT-060 dag 3, finding 6; toegezegd door de Dag-2-brief)."""
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


class SkillImportRowSchema(BaseModel):
    name: str
    category: str | None = None

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, value: object) -> object:
        return _blank_to_none(value)


class RoleRequirementImportRowSchema(BaseModel):
    role_name: str
    skill_name: str
    required_level: int


class EmployeeAssessmentImportRowSchema(BaseModel):
    user_email: str
    skill_name: str
    level: int


class TrainingImportRowSchema(BaseModel):
    name: str
    description: str | None = None
    skill_name: str | None = None

    @field_validator("description", "skill_name", mode="before")
    @classmethod
    def _normalize_optional_fields(cls, value: object) -> object:
        return _blank_to_none(value)


class EmployeeTrainingImportRowSchema(BaseModel):
    user_email: str
    training_name: str
    status: str = "assigned"

    @field_validator("status", mode="before")
    @classmethod
    def _default_status_when_blank(cls, value: object) -> object:
        # `status` heeft geen `None`-tak (het is een gesloten vocabulaire, geen "geen
        # koppeling") -- een lege cel valt terug op de default, niet op None.
        if isinstance(value, str) and value.strip() == "":
            return "assigned"
        return value


class ImportRowErrorResponse(BaseModel):
    row_index: int
    message: str


class ImportResultResponse(BaseModel):
    inserted: int
    updated: int
    errors: list[ImportRowErrorResponse]


class TrainingProposalCreateRequest(BaseModel):
    """Een voorstel aanmaken voor een functie en vaardigheid met een kloof.

    `extra="forbid"`: een `tenant_id` (of elk ander onbekend veld) in het verzoek wordt geweigerd
    (422). De tenant komt uit de sessie, nooit uit het verzoek.
    """

    model_config = ConfigDict(extra="forbid")

    role_name: str = Field(min_length=1, max_length=100)
    skill_name: str = Field(min_length=1, max_length=100)
    training_name: str = Field(min_length=1, max_length=150)


DeadlineKind = Literal["contract_einde", "verzuim", "certificaat"]


def _controleer_termijnregel(
    kind: str,
    start_date: date | None,
    end_date: date | None,
    description: str | None,
    analysis_date: date | None = None,
) -> None:
    """Verzuim: een startdatum en GEEN omschrijving (de werkgever registreert de ziekte niet).
    De andere soorten: een einddatum. Dezelfde regel staat als CHECK in de database."""
    if kind == "verzuim":
        if start_date is None:
            raise ValueError("start_date: verzuim vraagt de eerste ziektedag")
        if description:
            raise ValueError(
                "description: bij verzuim wordt geen omschrijving bewaard (geen diagnose of "
                "ziekteoorzaak registreren)"
            )
        if analysis_date is not None and analysis_date < start_date:
            raise ValueError(
                "analysis_date: de probleemanalyse kan niet voor de eerste ziektedag liggen"
            )
    elif end_date is None:
        raise ValueError("end_date: vul de einddatum in")


class DeadlineCreateRequest(BaseModel):
    """Een termijn vastleggen. `extra="forbid"`: een `tenant_id` in het verzoek geeft 422."""

    model_config = ConfigDict(extra="forbid")

    user_email: str = Field(min_length=3, max_length=320)
    kind: DeadlineKind
    start_date: date | None = None
    end_date: date | None = None
    analysis_date: date | None = None
    description: str | None = Field(default=None, max_length=200)

    @field_validator("description", mode="before")
    @classmethod
    def _lege_omschrijving_is_geen_omschrijving(cls, value: object) -> object:
        return _blank_to_none(value)

    @model_validator(mode="after")
    def _regel(self) -> "DeadlineCreateRequest":
        _controleer_termijnregel(
            self.kind, self.start_date, self.end_date, self.description, self.analysis_date
        )
        return self


class DeadlineUpdateRequest(BaseModel):
    """Status en/of de datum van de probleemanalyse wijzigen."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["open", "afgerond"] | None = None
    analysis_date: date | None = None
    done_label: str | None = Field(default=None, min_length=1, max_length=60)

    @model_validator(mode="after")
    def _minstens_een(self) -> "DeadlineUpdateRequest":
        if self.status is None and self.analysis_date is None and self.done_label is None:
            raise ValueError("geef een status, een analysedatum of een afgeronde termijn op")
        return self


class DeadlineImportRowSchema(BaseModel):
    """Een rij uit het CSV-bestand met termijnen."""

    user_email: str = Field(max_length=320)
    kind: DeadlineKind
    start_date: date | None = None
    end_date: date | None = None
    analysis_date: date | None = None
    description: str | None = Field(default=None, max_length=200)

    @field_validator("start_date", "end_date", "analysis_date", "description", mode="before")
    @classmethod
    def _leeg_is_geen_waarde(cls, value: object) -> object:
        return _blank_to_none(value)

    @model_validator(mode="after")
    def _regel(self) -> "DeadlineImportRowSchema":
        _controleer_termijnregel(
            self.kind, self.start_date, self.end_date, self.description, self.analysis_date
        )
        return self
