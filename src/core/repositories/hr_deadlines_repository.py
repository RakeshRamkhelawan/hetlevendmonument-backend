"""Termijnen (HR-pilot dag 3): vastleggen, wijzigen en de lijst "Komende termijnen".

Elke query filtert EXPLICIET op `tenant_id` (CLAUDE.md regel 11); de tenant komt van de aanroeper,
uit de JWT-context, nooit uit invoer. De signaaldata worden hier BEREKEND via
`hr_deadline_rules`, niet uit de database gelezen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.hr_deadline_models import HRDeadline
from src.core.models.rbac_models import User
from src.core.repositories.hr_import_types import ImportRowError
from src.core.utils.hr_deadline_rules import SOORT_VERZUIM, afgeleide_termijnen

STATUS_OPEN = "open"
STATUS_AFGEROND = "afgerond"
#: Het venster van de lijst: wat er de komende zestig dagen aankomt (plus wat al te laat is).
VENSTER_DAGEN = 60


class UnknownEmployee(Exception):
    """Het e-mailadres hoort bij geen medewerker van deze tenant."""


class AnalysisBeforeStart(Exception):
    """De datum van de probleemanalyse ligt voor de eerste ziektedag."""


@dataclass(frozen=True)
class DeadlineInput:
    user_email: str
    kind: str
    start_date: date | None
    end_date: date | None
    analysis_date: date | None
    description: str | None


@dataclass(frozen=True)
class UpcomingItem:
    deadline_id: int
    employee_id: int
    employee_email: str
    kind: str
    label: str
    datum: date
    bron: str
    toelichting: str
    te_laat: bool
    description: str | None


class HRDeadlinesRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _user_id(self, tenant_id: int, email: str) -> int | None:
        return (
            await self._db.execute(
                select(User.id).where(
                    User.tenant_id == tenant_id,
                    User.deleted_at.is_(None),
                    User.email == email.strip(),
                )
            )
        ).scalar_one_or_none()

    async def add(self, tenant_id: int, created_by: int, invoer: DeadlineInput) -> int:
        """Een regel vastleggen. `UnknownEmployee` als de medewerker niet bestaat."""
        user_id = await self._user_id(tenant_id, invoer.user_email)
        if user_id is None:
            raise UnknownEmployee(invoer.user_email)
        rij = HRDeadline(
            tenant_id=tenant_id,
            user_id=user_id,
            kind=invoer.kind,
            start_date=invoer.start_date,
            end_date=invoer.end_date,
            analysis_date=invoer.analysis_date,
            description=invoer.description,
            status=STATUS_OPEN,
            created_by=created_by,
        )
        self._db.add(rij)
        await self._db.flush()
        return int(rij.id)

    async def add_many(
        self, tenant_id: int, created_by: int, invoer: list[DeadlineInput]
    ) -> tuple[int, list[ImportRowError]]:
        """Alle geldige regels vastleggen; een onbekende medewerker wordt een foutregel.

        De foutregel telt vanaf 1 over de AANGEBODEN lijst (de aanroeper zet dat terug naar het
        bestandsrijnummer, zie `remap_repository_errors`).
        """
        fouten: list[ImportRowError] = []
        aantal = 0
        for positie, regel in enumerate(invoer, start=1):
            try:
                await self.add(tenant_id, created_by, regel)
            except UnknownEmployee:
                fouten.append(
                    ImportRowError(positie, "user_email: onbekende medewerker in deze omgeving")
                )
                continue
            aantal += 1
        return aantal, fouten

    async def update(
        self,
        tenant_id: int,
        deadline_id: int,
        *,
        status: str | None,
        analysis_date: date | None,
        done_label: str | None = None,
    ) -> bool:
        """Status, analysedatum en/of een afgeronde termijn. False: niet gevonden in deze tenant."""
        rij = (
            await self._db.execute(
                select(HRDeadline).where(
                    HRDeadline.id == deadline_id, HRDeadline.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        if rij is None:
            return False
        if (
            analysis_date is not None
            and rij.start_date is not None
            and analysis_date < rij.start_date
        ):
            raise AnalysisBeforeStart()
        if status is not None:
            rij.status = status
        if analysis_date is not None:
            rij.analysis_date = analysis_date
        if done_label is not None and done_label not in (rij.done_labels or []):
            # Een NIEUWE lijst toekennen: een JSON-kolom ziet een wijziging op hetzelfde object niet.
            rij.done_labels = [*(rij.done_labels or []), done_label]
        await self._db.flush()
        return True

    async def upcoming(
        self, tenant_id: int, vandaag: date, venster_dagen: int = VENSTER_DAGEN
    ) -> list[UpcomingItem]:
        """De berekende termijnen van OPEN regels tot en met `vandaag + 60 dagen`, op datum.

        Wat al voorbij is blijft staan (`te_laat`) zolang de regel open is: een gemiste termijn
        mag niet uit beeld verdwijnen.
        """
        grens = vandaag + timedelta(days=venster_dagen)
        rijen = (
            await self._db.execute(
                select(HRDeadline, User.email, User.id)
                .join(User, User.id == HRDeadline.user_id)
                .where(
                    HRDeadline.tenant_id == tenant_id,
                    User.tenant_id == tenant_id,
                    # Wie uit dienst is (AVG: zacht verwijderd) blijft niet in de lijst staan.
                    User.deleted_at.is_(None),
                    HRDeadline.status == STATUS_OPEN,
                )
            )
        ).all()
        items: list[UpcomingItem] = []
        for rij, email, employee_id in rijen:
            for termijn in afgeleide_termijnen(
                rij.kind,
                start_date=rij.start_date,
                end_date=rij.end_date,
                analysis_date=rij.analysis_date,
            ):
                # Is de probleemanalyse al gedaan (datum ingevuld), dan is die termijn voorbij.
                if (
                    rij.kind == SOORT_VERZUIM
                    and rij.analysis_date is not None
                    and termijn.label == "Probleemanalyse"
                ):
                    continue
                if termijn.label in (rij.done_labels or []):
                    continue
                if termijn.datum > grens:
                    continue
                items.append(
                    UpcomingItem(
                        deadline_id=int(rij.id),
                        employee_id=int(employee_id),
                        employee_email=email,
                        kind=rij.kind,
                        label=termijn.label,
                        datum=termijn.datum,
                        bron=termijn.bron,
                        toelichting=termijn.toelichting,
                        te_laat=termijn.datum < vandaag,
                        description=rij.description,
                    )
                )
        items.sort(key=lambda i: (i.datum, i.deadline_id, i.label))
        return items
