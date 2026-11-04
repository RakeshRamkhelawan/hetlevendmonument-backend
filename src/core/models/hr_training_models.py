"""Trainings-catalogus en medewerker-koppeling -- vervolg op ADR-036 OP-26 (Fase 3, BE-AGT-058).

`analyze_skill_gap` (`hr_skills_models.py`, `hr_registry.py`) kan een tekort aan een vaardigheid
melden, maar er was nergens een tabel die een training aan die vaardigheid koppelt, of
bijhoudt wie een training heeft gevolgd. `trainings` is de catalogus (analoog aan `skills`);
`employee_trainings` is de koppeling naar wie wat heeft gedaan (analoog aan `employee_skills`).
Deze module koppelt de gap-analyse NOG NIET aan trainings -- dat is bewust uitgesteld naar een
latere sprint, om scope-vervaging met D11 te voorkomen.

**Waarom geen `employees`-tabel, waarom `skill_id` optioneel op `Training`.** Zelfde
redenering als `hr_skills_models.py`: een medewerker IS een gebruiker, een functie IS een rol.
Niet elke training hoort bij een specifieke vaardigheid (bv. een algemene onboarding-cursus),
dus `skill_id` is nullable.

**Privacy.** `employee_trainings` is, net als `employee_skills`, een gegeven over een individuele
medewerker in een arbeidsverhouding (welke training, wanneer, welke status) en daarmee een
persoonsgegeven. Dezelfde twee gevolgen als bij `employee_skills` horen hier niet in de module
maar wel erbij: er moet een grondslag en bewaartermijn voor zijn, en zodra hier echte gegevens
in staan beoordeelt het systeem individuele werknemers. Vandaag leest niets deze tabel uit
(geen tool bestaat nog) -- die afweging komt terug zodra een leespad wordt gebouwd.

**Bekend, gedocumenteerd gat: enkelvoudige FKs, geen composite FKs (ADR-005 par. 5).**
`role_id`/`skill_id`/`user_id`/`training_id` zijn enkelvoudige foreign keys, niet de
samengestelde `(tenant_id, id)`-vorm die ADR-005 par. 5 (toegevoegd 2026-08-21) voorschrijft
voor koppeltabellen. Zonder samengestelde FK controleert de database niet dat de gekoppelde rij
(bv. een `Skill`) bij DEZELFDE tenant hoort als de koppelrij zelf -- alleen de ORM-laag
(ADR-004 `do_orm_execute`-hook) en RLS (vandaag zonder `FORCE`, dus omzeilbaar door de
table-owner-verbinding die deze applicatie gebruikt) beschermen daartegen. Dit is HETZELFDE
gat als op de al-bestaande `role_required_skills`/`employee_skills` (`hr_skills_models.py`,
sinds 2026-08-15) -- bewust NIET hier als eerste, in isolatie, met een nieuw patroon gefixed
(Rakesh's beslissing 2026-08-22, Fase 3): dat zou een derde, inconsistente aanpak naast de twee
bestaande tabellen introduceren terwijl de bredere remediatie (`docs/audits/
MULTI_TENANT_INTEGRITY_AND_RLS_AUDIT_2026-08-21.md`) nog niet is uitgevoerd. Bewaakt door
`tests/architecture/test_hr_junction_tables_composite_fk_gap.py` (gedateerde uitzondering +
staleness-test), zodat dit gat niet stilzwijgend kan uitbreiden zonder het te registreren.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base

#: Gesloten vocabulaire voor `EmployeeTraining.status` -- een module-constante i.p.v. de
#: waarden alleen in de CHECK-constraint-string, zodat een toekomstige API-schema/service-laag
#: (Dag 3+) dezelfde bron kan hergebruiken in plaats van de tekenreeksen te herhalen.
EMPLOYEE_TRAINING_STATUSES = ("assigned", "in_progress", "completed")

#: Gesloten vocabulaire voor `TrainingProposal.status` (HR-pilot dag 2).
TRAINING_PROPOSAL_STATUSES = ("voorgesteld", "goedgekeurd", "afgewezen")


class Training(Base):  # type: ignore[misc]
    """Een training in de catalogus van een tenant.

    `name` is `String(150)`, breder dan `Skill.name`'s `String(100)`: trainingstitels/
    certificeringen lopen doorgaans langer dan korte vaardigheid-tags (bv. "Certified
    International Financial Reporting Standards Practitioner").
    """

    __tablename__ = "trainings"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_trainings_tenant_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    skill_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("skills.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EmployeeTraining(Base):  # type: ignore[misc]
    """Of, en in welke status, een medewerker een training heeft gevolgd.

    `training_id` is `ondelete="CASCADE"`: verwijdert een tenant-admin een training uit de
    catalogus, dan verdwijnt ook de bijbehorende afrondingshistorie. Dat is een bewuste keuze
    die past bij het huidige gebruik (geen leespad leest deze tabel nog); zodra een audit- of
    compliance-leespad hierop gebouwd wordt, moet deze keuze opnieuw worden afgewogen tegen
    een archiveringsvlag in plaats van een harde verwijdering.
    """

    __tablename__ = "employee_trainings"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "training_id",
            name="uq_employee_trainings_tenant_user_training",
        ),
        CheckConstraint(
            "status IN (" + ",".join(f"'{s}'" for s in EMPLOYEE_TRAINING_STATUSES) + ")",
            name="ck_employee_trainings_status",
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
    training_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trainings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="assigned", server_default="assigned"
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TrainingProposal(Base):  # type: ignore[misc]
    """Een voorstel om een medewerker een training te laten volgen (HR-pilot dag 2).

    Een voorstel is een RIJ en geen vrije tekst: een mens (`hr:approve`) keurt het goed of af, en
    pas bij goedkeuren wordt de training toegewezen -- via hetzelfde pad als de agent-tool
    `schedule_training`, dus er is geen tweede schrijfweg naar `employee_trainings`.

    Een medewerker mag maar EEN open voorstel per vaardigheid hebben (gedeeltelijke unieke index
    op `voorgesteld`); een afgewezen of goedgekeurd voorstel blokkeert een nieuw niet.

    Enkelvoudige FKs, net als `employee_trainings` (zie de moduledocstring over ADR-005 par. 5):
    de repository filtert elke query expliciet op `tenant_id`.
    """

    __tablename__ = "training_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ",".join(f"'{s}'" for s in TRAINING_PROPOSAL_STATUSES) + ")",
            name="ck_training_proposals_status",
        ),
        Index(
            "uq_training_proposals_open",
            "tenant_id",
            "user_id",
            "skill_id",
            unique=True,
            postgresql_where=text("status = 'voorgesteld'"),
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
    training_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trainings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="voorgesteld", server_default="voorgesteld"
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
