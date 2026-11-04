"""Opleidingsvoorstellen (HR-pilot dag 2): aanmaken uit de kloof, lezen, beslissen.

Elke query filtert EXPLICIET op `tenant_id` (CLAUDE.md regel 11; de ADR-004-hook is niet in elke
context geregistreerd). De tenant komt van de aanroeper, uit de JWT-context, nooit uit invoer.

Een voorstel is een rij. Wie niet voldoet is iemand met een BEOORDEELD niveau onder de eis: wie
nooit beoordeeld is, telt niet mee (niet gemeten is iets anders dan niet kunnen; zie
`HRToolRegistry._build_gap_statement`).

Bij elk voorstel hoort een uitleg (`build_explanation`, AI-verordening art. 13 en art. 86). Die komt
uit dezelfde rijen; er is geen taalmodel in de keten die een voorstel maakt.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy import Row, Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.core.models.hr_skills_models import EmployeeSkill, RoleRequiredSkill, Skill
from src.core.models.hr_training_models import Training, TrainingProposal
from src.core.models.rbac_models import Role, User, user_roles

#: Een rij van `_rijen_query`: het voorstel, e-mail van medewerker, vaardigheid, opleiding, e-mail van
#: maker en besluiter, het vereiste niveau, het gemeten niveau en de beoordelingsdatum. Zo leest
#: pyright de query af; de uiterlijke joins kunnen in werkelijkheid ook `None` geven.
_RijTuple = tuple[TrainingProposal, str, str, str, str, str, int, int, datetime | None]

STATUS_VOORGESTELD = "voorgesteld"
STATUS_GOEDGEKEURD = "goedgekeurd"
STATUS_AFGEWEZEN = "afgewezen"


class ProposalInputNotFound(Exception):
    """De functie, vaardigheid, eis of training bestaat niet binnen deze tenant."""

    def __init__(self, soort: str) -> None:
        super().__init__(soort)
        self.soort = soort


@dataclass(frozen=True)
class ProposalRow:
    id: int
    user_id: int
    employee_email: str
    skill_name: str
    training_name: str
    reason: str
    status: str
    created_at: datetime | None
    created_by_email: str | None
    decided_at: datetime | None
    decided_by_email: str | None
    # De gegevens voor de uitleg (AI-verordening art. 13 en 86): het niveau dat de functie eist, het
    # HUIDIGE gemeten niveau en de datum van die beoordeling. `reason` blijft de bevroren tekst van
    # het moment waarop het voorstel is gemaakt.
    required_level: int | None
    measured_level: int | None
    assessed_at: datetime | None


@dataclass(frozen=True)
class ProposalCreateOutcome:
    created: int
    skipped: int


@dataclass(frozen=True)
class ProposalToDecide:
    """Wat de router nodig heeft om te beslissen, zonder het ORM-object te lekken."""

    id: int
    status: str
    created_by: int | None
    employee_email: str
    training_name: str


class HRTrainingProposalsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_from_gap(
        self,
        tenant_id: int,
        created_by: int,
        *,
        role_name: str,
        skill_name: str,
        training_name: str,
    ) -> ProposalCreateOutcome:
        """Per medewerker in de functie die onder de eis zit een voorstel; bestaande blijven."""
        db = self._db
        eis = (
            await db.execute(
                select(RoleRequiredSkill.required_level, Skill.id, Role.id)
                .join(Role, and_(Role.id == RoleRequiredSkill.role_id, Role.tenant_id == tenant_id))
                .join(
                    Skill,
                    and_(Skill.id == RoleRequiredSkill.skill_id, Skill.tenant_id == tenant_id),
                )
                .where(
                    RoleRequiredSkill.tenant_id == tenant_id,
                    Role.name == role_name,
                    Skill.name == skill_name,
                )
            )
        ).first()
        if eis is None:
            raise ProposalInputNotFound("eis")
        required_level, skill_id, role_id = eis
        training_id = (
            await db.execute(
                select(Training.id).where(
                    Training.tenant_id == tenant_id, Training.name == training_name
                )
            )
        ).scalar_one_or_none()
        if training_id is None:
            raise ProposalInputNotFound("training")

        onder_de_eis = (
            await db.execute(
                select(User.id, EmployeeSkill.level)
                .join(user_roles, user_roles.c.user_id == User.id)
                .join(
                    EmployeeSkill,
                    and_(
                        EmployeeSkill.user_id == User.id,
                        EmployeeSkill.skill_id == skill_id,
                        EmployeeSkill.tenant_id == tenant_id,
                    ),
                )
                .where(
                    user_roles.c.role_id == role_id,
                    User.tenant_id == tenant_id,
                    User.deleted_at.is_(None),
                    EmployeeSkill.level < required_level,
                )
                .order_by(User.id)
            )
        ).all()

        bestaand = set(
            (
                await db.execute(
                    select(TrainingProposal.user_id).where(
                        TrainingProposal.tenant_id == tenant_id,
                        TrainingProposal.skill_id == skill_id,
                        TrainingProposal.status == STATUS_VOORGESTELD,
                    )
                )
            )
            .scalars()
            .all()
        )
        # Een GOEDGEKEURD voorstel voor dezelfde medewerker, vaardigheid en opleiding telt ook als
        # bestaand: de unieke index dekt alleen OPEN voorstellen, en zonder deze controle liet een
        # tweede aanroep na het goedkeuren een duplicaat toe (gemeten bij de acceptatie).
        goedgekeurd = set(
            (
                await db.execute(
                    select(TrainingProposal.user_id).where(
                        TrainingProposal.tenant_id == tenant_id,
                        TrainingProposal.skill_id == skill_id,
                        TrainingProposal.training_id == training_id,
                        TrainingProposal.status == STATUS_GOEDGEKEURD,
                    )
                )
            )
            .scalars()
            .all()
        )
        aangemaakt = 0
        overgeslagen = 0
        for user_id, level in onder_de_eis:
            if user_id in bestaand or user_id in goedgekeurd:
                overgeslagen += 1
                continue
            db.add(
                TrainingProposal(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    skill_id=skill_id,
                    training_id=training_id,
                    reason=(
                        f"Niveau {level} van het gevraagde niveau {required_level} "
                        f"voor {role_name} ({skill_name})"
                    ),
                    status=STATUS_VOORGESTELD,
                    created_by=created_by,
                )
            )
            aangemaakt += 1
        await db.flush()
        return ProposalCreateOutcome(created=aangemaakt, skipped=overgeslagen)

    def _rijen_query(self, tenant_id: int) -> Select[_RijTuple]:
        """Een voorstel met alles wat de lijst en de uitleg nodig hebben; ALTIJD op deze tenant."""
        employee = aliased(User)
        maker = aliased(User)
        besluiter = aliased(User)
        # Het hoogste niveau dat een van de functies van de medewerker voor deze vaardigheid eist.
        vereist = (
            select(func.max(RoleRequiredSkill.required_level))
            .join(
                user_roles,
                and_(
                    user_roles.c.role_id == RoleRequiredSkill.role_id,
                    user_roles.c.tenant_id == tenant_id,
                ),
            )
            .where(
                user_roles.c.user_id == TrainingProposal.user_id,
                RoleRequiredSkill.skill_id == TrainingProposal.skill_id,
                RoleRequiredSkill.tenant_id == tenant_id,
            )
            .scalar_subquery()
        )
        return (
            select(
                TrainingProposal,
                employee.email,
                Skill.name,
                Training.name,
                maker.email,
                besluiter.email,
                vereist,
                EmployeeSkill.level,
                EmployeeSkill.assessed_at,
            )
            .join(employee, employee.id == TrainingProposal.user_id)
            .join(Skill, Skill.id == TrainingProposal.skill_id)
            .join(Training, Training.id == TrainingProposal.training_id)
            .outerjoin(maker, maker.id == TrainingProposal.created_by)
            .outerjoin(besluiter, besluiter.id == TrainingProposal.decided_by)
            .outerjoin(
                EmployeeSkill,
                and_(
                    EmployeeSkill.user_id == TrainingProposal.user_id,
                    EmployeeSkill.skill_id == TrainingProposal.skill_id,
                    EmployeeSkill.tenant_id == tenant_id,
                ),
            )
            .where(
                TrainingProposal.tenant_id == tenant_id,
                employee.tenant_id == tenant_id,
                Skill.tenant_id == tenant_id,
                Training.tenant_id == tenant_id,
            )
        )

    @staticmethod
    def _als_rijen(rijen: Sequence[Row[_RijTuple]]) -> list[ProposalRow]:
        return [
            ProposalRow(
                id=p.id,
                user_id=p.user_id,
                employee_email=e,
                skill_name=s,
                training_name=t,
                reason=p.reason,
                status=p.status,
                created_at=p.created_at,
                created_by_email=m,
                decided_at=p.decided_at,
                decided_by_email=b,
                required_level=vereist,
                measured_level=niveau,
                assessed_at=beoordeeld,
            )
            for p, e, s, t, m, b, vereist, niveau, beoordeeld in rijen
        ]

    async def list_proposals(self, tenant_id: int, *, limit: int, offset: int) -> list[ProposalRow]:
        rijen = (
            await self._db.execute(
                self._rijen_query(tenant_id)
                .order_by(TrainingProposal.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return self._als_rijen(rijen)

    async def get_proposal(self, tenant_id: int, proposal_id: int) -> ProposalRow | None:
        rij = (
            await self._db.execute(
                self._rijen_query(tenant_id).where(TrainingProposal.id == proposal_id)
            )
        ).all()
        return self._als_rijen(rij)[0] if rij else None

    async def list_for_user(
        self, tenant_id: int, user_id: int, *, limit: int, offset: int
    ) -> list[ProposalRow]:
        """De voorstellen van EEN medewerker (de aanroeper zelf); nooit die van een collega."""
        rijen = (
            await self._db.execute(
                self._rijen_query(tenant_id)
                .where(TrainingProposal.user_id == user_id)
                .order_by(TrainingProposal.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return self._als_rijen(rijen)

    async def get_for_user(
        self, tenant_id: int, user_id: int, proposal_id: int
    ) -> ProposalRow | None:
        """Een voorstel, ALLEEN als het van deze medewerker is; anders None (de route geeft 404)."""
        rij = (
            await self._db.execute(
                self._rijen_query(tenant_id).where(
                    TrainingProposal.id == proposal_id, TrainingProposal.user_id == user_id
                )
            )
        ).all()
        return self._als_rijen(rij)[0] if rij else None

    async def get_to_decide(self, tenant_id: int, proposal_id: int) -> ProposalToDecide | None:
        rij = (
            await self._db.execute(
                select(TrainingProposal, User.email, Training.name)
                .join(User, User.id == TrainingProposal.user_id)
                .join(Training, Training.id == TrainingProposal.training_id)
                .where(
                    TrainingProposal.id == proposal_id,
                    TrainingProposal.tenant_id == tenant_id,
                    User.tenant_id == tenant_id,
                    Training.tenant_id == tenant_id,
                )
            )
        ).first()
        if rij is None:
            return None
        voorstel, email, training = rij
        return ProposalToDecide(
            id=voorstel.id,
            status=voorstel.status,
            created_by=voorstel.created_by,
            employee_email=email,
            training_name=training,
        )

    async def mark_decided(
        self, tenant_id: int, proposal_id: int, *, status: str, decided_by: int
    ) -> bool:
        """Zet de status, ALLEEN als het voorstel nog `voorgesteld` is. False: al beslist."""
        voorstel = (
            await self._db.execute(
                select(TrainingProposal)
                .where(
                    TrainingProposal.id == proposal_id,
                    TrainingProposal.tenant_id == tenant_id,
                    TrainingProposal.status == STATUS_VOORGESTELD,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if voorstel is None:
            return False
        voorstel.status = status
        voorstel.decided_by = decided_by
        voorstel.decided_at = datetime.now(timezone.utc)
        await self._db.flush()
        return True


def _datum(moment: datetime | None) -> str:
    return moment.date().isoformat() if moment else "onbekend"


def build_explanation(rij: ProposalRow, *, voor_medewerker: bool = False) -> dict[str, object]:
    """De uitleg bij een voorstel, in gewone taal (AI-verordening art. 13 en art. 86).

    Alles komt uit bestaande rijen; er is geen taalmodel in de keten die dit voorstel maakt
    (`create_from_gap` rekent met een SQL-vergelijking). `voor_medewerker` laat de naam van de
    besluitnemer weg: de medewerker ziet WAT er besloten is, niet welke collega dat deed.

    Het gemeten niveau is het HUIDIGE. Is de vaardigheid beoordeeld NA het maken van het voorstel,
    dan zegt de uitleg dat, en blijft `reason_at_proposal` de tekst van toen.
    """
    opnieuw_beoordeeld = bool(
        rij.assessed_at and rij.created_at and rij.assessed_at > rij.created_at
    )
    haalt_eis_nu = (
        rij.measured_level is not None
        and rij.required_level is not None
        and rij.measured_level >= rij.required_level
    )
    if rij.measured_level is None or rij.required_level is None:
        niveau_zin = (
            f"Voor de vaardigheid {rij.skill_name} is het niveau of de eis niet meer beschikbaar."
        )
        aanleiding = "Deze opleiding is voorgesteld omdat het niveau onder de eis lag."
    elif haalt_eis_nu:
        # Het voorstel is gemaakt toen het niveau onder de eis lag; de huidige beoordeling haalt
        # de eis wel. Zeggen dat het niveau "onder de eis" ligt zou nu onwaar zijn (Gate 2).
        # Dat het niveau toen LAGER was is alleen bewezen na een nieuwe beoordeling; zonder die kan
        # ook de eis zijn verlaagd of de medewerker van functie zijn gewisseld (herreview).
        verschil_zin = (
            "Het voorstel is gemaakt toen het niveau lager was."
            if opnieuw_beoordeeld
            else "Sinds het voorstel is de eis of het niveau veranderd; de reden van toen staat bij "
            "de gegevens van het voorstel."
        )
        niveau_zin = (
            f"Het huidige niveau van de vaardigheid {rij.skill_name} is {rij.measured_level} en "
            f"haalt de eis ({rij.required_level}) nu. {verschil_zin} Het huidige niveau is "
            f"beoordeeld op {_datum(rij.assessed_at)}."
        )
        aanleiding = (
            f"Deze opleiding ({rij.training_name}) is voorgesteld omdat het niveau onder de eis "
            "lag toen het voorstel werd gemaakt."
        )
    else:
        niveau_zin = (
            f"Het gemeten niveau van de vaardigheid {rij.skill_name} is {rij.measured_level}, "
            f"onder het gevraagde niveau {rij.required_level}. "
            f"Dat niveau is beoordeeld op {_datum(rij.assessed_at)}."
        )
        werkwoord = "wordt" if rij.status == STATUS_VOORGESTELD else "is"
        aanleiding = (
            f"Deze opleiding ({rij.training_name}) {werkwoord} voorgesteld omdat het niveau "
            "onder de eis ligt."
        )
    delen = [aanleiding, niveau_zin]
    if opnieuw_beoordeeld:
        delen.append(
            "Let op: de vaardigheid is opnieuw beoordeeld nadat dit voorstel is gemaakt. Het niveau "
            "hierboven is de huidige beoordeling; de reden van toen staat bij de gegevens van het "
            "voorstel."
        )
    delen.append(
        "Het voorstel is met vaste regels berekend (een vergelijking van niveaus); er is geen "
        "taalmodel aan te pas gekomen. De opleiding is gekozen door een medewerker van "
        "personeelszaken. Een mens besluit of de opleiding wordt toegewezen: zonder dat besluit "
        "gebeurt er niets."
    )
    if rij.status != STATUS_VOORGESTELD:
        delen.append(
            f"Besluit: {rij.status} op {_datum(rij.decided_at)}, door een mens van personeelszaken."
        )
    uitleg: dict[str, object] = {
        "proposal_id": rij.id,
        "skill": rij.skill_name,
        "training": rij.training_name,
        "required_level": rij.required_level,
        "measured_level": rij.measured_level,
        "assessed_at": rij.assessed_at.isoformat() if rij.assessed_at else None,
        "reassessed_since_proposal": opnieuw_beoordeeld,
        "reason_at_proposal": rij.reason,
        "rule_based": True,
        "human_decides": True,
        "status": rij.status,
        "created_at": rij.created_at.isoformat() if rij.created_at else None,
        "decided_at": rij.decided_at.isoformat() if rij.decided_at else None,
        "text": " ".join(delen),
    }
    if not voor_medewerker:
        uitleg["decided_by_email"] = rij.decided_by_email
    return uitleg
