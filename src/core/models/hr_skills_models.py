"""Vaardigheden, functie-eisen en beoordelingen -- het datamodel achter ADR-036 OP-26.

De piloot van D10 (`skillsgaptraining`) moest een vaardighedenkloof bepalen, maar er was
nergens in het platform een tabel met vaardigheden, functie-eisen of beoordelingen. De enige
HR-tool die bestond (`query_hr_database`) telde koppen per rol uit de RBAC-tabellen. Daarmee
kun je zeggen hoeveel mensen een functie bekleden, niet wat ze missen.

**Waarom geen `employees`-tabel.** Die zou een tweede waarheid over dezelfde mensen zijn.
`users` en `roles` bestaan al, dragen al `tenant_id NOT NULL` (ADR-005) en worden al door de
AVG-wisroute geraakt (`dsar_service` zet `deleted_at`). Een aparte medewerkerstabel zou al die
machinerie moeten dupliceren, inclusief de wissing -- en een gemiste kopie is precies hoe
persoonsgegevens blijven staan nadat iemand om verwijdering heeft gevraagd. Een medewerker IS
hier een gebruiker; een functie IS een rol.

**Waarom drie tabellen en niet twee.** De catalogus (`skills`) staat los van beide koppelingen,
zodat "IFRS" een ding is en niet een tekenreeks die in twintig rijen anders gespeld staat. Een
kloof is daarna een aftreksom: wat de rol eist (`role_required_skills`) min wat de bezetters
kunnen (`employee_skills`).

**Privacy.** `employee_skills` is een beoordeling van een persoon en daarmee een
persoonsgegeven in een arbeidsverhouding. Twee gevolgen die niet in deze module thuishoren
maar er wel bij horen: er moet een grondslag en een bewaartermijn voor zijn, en zodra hier
echte gegevens in staan beoordeelt het systeem individuele werknemers -- alle vier de
HR-skills (`employeesentiment`, `internalmobility`, `talentacquisition` en `skillsgaptraining`)
staan om die reden op `annex_iii` in hun manifest (gemeten 2026-10-14; de zin dat
`skillsgaptraining` nog op `none` stond was verouderd). Wat dat in de code doet:
`BaseSpecialistAgent._floor_applies_to` stuurt ELKE actie van zo'n skill, ook lezen, langs een
mens (HITL); verder gebruikt niets de classificatie.

De opleidingsvoorstellen (`training_proposals`) worden NIET door die agent gemaakt maar met een
SQL-vergelijking van niveaus (`HRTrainingProposalsRepository.create_from_gap`): er zit geen
taalmodel in de keten die een voorstel maakt. De agent `skillsgaptraining` (`technology: llm`)
schrijft wel een vrije-tekstadvies en mag `schedule_training` aanroepen, altijd via een mens. Bij
elk voorstel hoort een uitleg in gewone taal (`build_explanation`, AI-verordening art. 13 en 86).
Besluit van Rakesh 2026-10-12: het HR-pakket wordt als hoog-risico behandeld.

Vandaag leest de bijbehorende tool uitsluitend GEAGGREGEERD (tellingen per rol en vaardigheid,
nooit een persoon), precies zoals `query_hr_database` een filter op `employee_id` al weigert.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base

#: Beoordelingsschaal. Vijf niveaus, laagste 1: een nul zou "niet beoordeeld" en "kan het
#: niet" op een hoop gooien, en dat verschil is nu juist waar een kloofanalyse over gaat.
MIN_SKILL_LEVEL = 1
MAX_SKILL_LEVEL = 5


class Skill(Base):  # type: ignore[misc]
    """Een vaardigheid in de catalogus van een tenant."""

    __tablename__ = "skills"
    __table_args__ = (
        # Per tenant uniek: twee tenants mogen allebei "IFRS" hebben, binnen een tenant niet.
        UniqueConstraint("tenant_id", "name", name="uq_skills_tenant_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RoleRequiredSkill(Base):  # type: ignore[misc]
    """Welk niveau een functie van een vaardigheid vraagt."""

    __tablename__ = "role_required_skills"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "role_id", "skill_id", name="uq_role_required_skills_tenant_role_skill"
        ),
        CheckConstraint(
            f"required_level >= {MIN_SKILL_LEVEL} AND required_level <= {MAX_SKILL_LEVEL}",
            name="ck_role_required_skills_level_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    required_level: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EmployeeSkill(Base):  # type: ignore[misc]
    """Het beoordeelde niveau van een medewerker op een vaardigheid.

    `assessed_by` mag leeg zijn en wordt bij verwijdering van de beoordelaar op NULL gezet:
    de beoordeling zelf blijft geldig als degene die hem gaf uit dienst is. Bij de BEOORDEELDE
    (`user_id`) gaat de rij wel mee -- wie gewist wordt, laat geen oordeel over zich achter.
    """

    __tablename__ = "employee_skills"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "user_id", "skill_id", name="uq_employee_skills_tenant_user_skill"
        ),
        CheckConstraint(
            f"level >= {MIN_SKILL_LEVEL} AND level <= {MAX_SKILL_LEVEL}",
            name="ck_employee_skills_level_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    assessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    assessed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
