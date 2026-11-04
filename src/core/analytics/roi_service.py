"""Rendementscijfers (ROI) in twee lagen: GEMETEN en GESCHAT (SP-KLANT-04).

**Gemeten** is wat de database weet over de runs van deze tenant: aantal, geslaagd, gefaald, items,
doorlooptijd, nakijken, kosten. **Geschat** is wat daaruit volgt als de KLANT zegt hoeveel handwerk
een item kost en wat een uur kost; zonder die aanname is er geen euro (`estimated` is dan `None`).
Een vast getal in code ("deze run bespaarde 2 uur, 150 euro") is geen meting maar een claim van ons,
waarvoor de bewijslast bij ons ligt (art. 6:195 BW); de vroegere `BASELINES` en `AVG_HOURLY_RATE`
zijn daarom weg.

Alleen per tenant en per pack, nooit per medewerker of afdeling (WOR art. 27 lid 1 sub l, AVG art. 88).

Schrijven en lezen gaan via de ORM met een expliciet tenantfilter naast de `do_orm_execute`-hook;
`record_run` doet GEEN `commit()`: de aanroeper bepaalt de transactie (in `packs.py` staat het in
`best_effort`).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.roi_models import RUN_STATUSSEN, AgentRunMetric, RoiAssumption

#: Een run zonder gemeten itemtelling telt als een item: het kleinste eerlijke aantal. Dit staat
#: ook zo in het antwoord, zodat het scherm het kan uitleggen.
ITEMS_PER_RUN_ALS_ONBEKEND = 1

_NIET_GESLAAGD = ("mislukt", "geblokkeerd", "meer_budget_nodig")
_ONBEKEND_PACK = "onbekend"


class AssumptionOut(BaseModel):
    pack_id: str
    manual_minutes_per_item: float
    hourly_rate_eur: float
    source: str
    set_at: datetime


class EstimatedOut(BaseModel):
    """De GESCHATTE laag: altijd samen met de aanname waarop hij rust."""

    items: int
    hours_saved: float
    savings_eur: float


class PackRoi(BaseModel):
    pack_id: str
    # Gemeten. Nakijkwerk (`needed_human_review`) staat bewust NIET in het antwoord: de kolom bestaat,
    # maar geen schrijver zet hem; een 0 zou als meting lezen.
    runs: int
    succeeded: int
    partial: int
    failed: int
    items_processed: int | None
    llm_cost_eur: float | None
    avg_duration_seconds: float | None
    # Geschat: alleen met een aanname van de klant
    assumption: AssumptionOut | None
    estimated: EstimatedOut | None


class MeasuredTotals(BaseModel):
    runs: int
    succeeded: int
    failed: int
    items_processed: int | None
    llm_cost_eur: float | None


class ROISummary(BaseModel):
    tenant_id: int
    measured: MeasuredTotals
    packs: list[PackRoi]
    # Som van de packs MET aanname; `None` als geen enkel pack er een heeft.
    estimated: EstimatedOut | None
    packs_without_assumption: list[str]


def schat_besparing(
    items: int, manual_minutes_per_item: float, hourly_rate_eur: float
) -> EstimatedOut:
    """items x minuten handwerk per item = uren; uren x uurtarief = euro's."""
    uren = items * manual_minutes_per_item / 60.0
    return EstimatedOut(items=items, hours_saved=uren, savings_eur=uren * hourly_rate_eur)


def _float_of_none(waarde: Decimal | float | int | None) -> float | None:
    return None if waarde is None else float(waarde)


def _aanname_out(rij: RoiAssumption) -> AssumptionOut:
    return AssumptionOut(
        pack_id=rij.pack_id,
        manual_minutes_per_item=float(rij.manual_minutes_per_item),
        hourly_rate_eur=float(rij.hourly_rate_eur),
        source=rij.source,
        set_at=rij.set_at,
    )


class ROIService:
    """Legt runs vast, bewaart de aannames van de klant en rekent de twee lagen uit."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record_run(
        self,
        *,
        tenant_id: int,
        agent_id: str,
        pack_id: str | None,
        task_id: str,
        status: str,
        started_at: datetime,
        finished_at: datetime,
        items_processed: int | None = None,
        needed_human_review: bool = False,
        llm_cost_eur: Decimal | float | None = None,
    ) -> None:
        """Voeg een run toe aan de meting. Geen `commit()`; geen medewerker, bewust.

        De INSERT loopt binnen `adopt_tenant`: onder de applicatierol met RLS weigert de database een
        INSERT zonder tenantcontext, en een run uit een worker of een achtergrondtaak heeft de
        ContextVar van het HTTP-verzoek niet. De aanroeper (`best_effort` in `packs.py`) zou die
        weigering slikken en de meting stil laten verdwijnen. Hier en niet in `packs.py`, zodat elke
        aanroeper het krijgt en `agent_runtime` geen extra koppeling naar de database-laag erbij krijgt.
        """
        from src.core.database.bypass_session import adopt_tenant

        if status not in RUN_STATUSSEN:
            raise ValueError(f"onbekende runstatus {status!r}; toegestaan: {RUN_STATUSSEN}")
        async with adopt_tenant(self.db, tenant_id):
            await self._voeg_run_toe(
                tenant_id=tenant_id,
                agent_id=agent_id,
                pack_id=pack_id,
                task_id=task_id,
                status=status,
                started_at=started_at,
                finished_at=finished_at,
                items_processed=items_processed,
                needed_human_review=needed_human_review,
                llm_cost_eur=llm_cost_eur,
            )

    async def _voeg_run_toe(
        self,
        *,
        tenant_id: int,
        agent_id: str,
        pack_id: str | None,
        task_id: str,
        status: str,
        started_at: datetime,
        finished_at: datetime,
        items_processed: int | None,
        needed_human_review: bool,
        llm_cost_eur: Decimal | float | None,
    ) -> None:
        self.db.add(
            AgentRunMetric(
                tenant_id=tenant_id,
                agent_id=agent_id,
                pack_id=pack_id,
                task_id=task_id,
                status=status,
                started_at=started_at,
                finished_at=finished_at,
                items_processed=items_processed,
                needed_human_review=needed_human_review,
                llm_cost_eur=None if llm_cost_eur is None else Decimal(str(llm_cost_eur)),
            )
        )
        await self.db.flush()

    async def list_assumptions(self, tenant_id: int) -> list[AssumptionOut]:
        rijen = await self.db.execute(
            select(RoiAssumption)
            .where(RoiAssumption.tenant_id == tenant_id)
            .order_by(RoiAssumption.pack_id)
        )
        return [_aanname_out(r) for r in rijen.scalars().all()]

    async def set_assumption(
        self,
        tenant_id: int,
        pack_id: str,
        manual_minutes_per_item: float,
        hourly_rate_eur: float,
    ) -> AssumptionOut:
        """Zet of vervang de aanname van de klant voor dit pack. Geen `commit()`.

        Een upsert op de unieke sleutel `(tenant_id, pack_id)`: twee gelijktijdige PUTs voor dezelfde
        tenant en pack botsen anders op die sleutel en geven een 500.
        """
        waarden = {
            "manual_minutes_per_item": Decimal(str(manual_minutes_per_item)),
            "hourly_rate_eur": Decimal(str(hourly_rate_eur)),
            "source": "klant_ingevuld",
            "set_at": func.now(),
        }
        stmt = (
            pg_insert(RoiAssumption)
            .values(tenant_id=tenant_id, pack_id=pack_id, **waarden)
            .on_conflict_do_update(constraint="uq_roi_assumptions_tenant_pack", set_=waarden)
            .returning(RoiAssumption)
        )
        rij = (await self.db.execute(stmt)).scalar_one()
        return _aanname_out(rij)

    async def get_tenant_roi(self, tenant_id: int) -> ROISummary:
        """De twee lagen voor deze tenant. Elke query filtert expliciet op `tenant_id`."""
        geslaagd = AgentRunMetric.status == "klaar"
        items_of_een = func.coalesce(AgentRunMetric.items_processed, ITEMS_PER_RUN_ALS_ONBEKEND)
        rijen = (
            await self.db.execute(
                select(
                    AgentRunMetric.pack_id,
                    func.count(),
                    func.sum(case((geslaagd, 1), else_=0)),
                    func.sum(case((AgentRunMetric.status == "gedeeltelijk", 1), else_=0)),
                    func.sum(case((AgentRunMetric.status.in_(_NIET_GESLAAGD), 1), else_=0)),
                    func.sum(AgentRunMetric.items_processed),
                    func.sum(case((geslaagd, items_of_een), else_=0)),
                    func.sum(AgentRunMetric.llm_cost_eur),
                    func.avg(
                        func.extract(
                            "epoch", AgentRunMetric.finished_at - AgentRunMetric.started_at
                        )
                    ),
                )
                .where(AgentRunMetric.tenant_id == tenant_id)
                .group_by(AgentRunMetric.pack_id)
                .order_by(AgentRunMetric.pack_id)
            )
        ).all()
        aannames = {a.pack_id: a for a in await self.list_assumptions(tenant_id)}

        packs: list[PackRoi] = []
        for (
            pack_id,
            runs,
            gelukt,
            gedeeltelijk,
            mislukt,
            items,
            items_voor_schatting,
            kosten,
            duur,
        ) in rijen:
            naam = pack_id or _ONBEKEND_PACK
            aanname = aannames.get(naam)
            packs.append(
                PackRoi(
                    pack_id=naam,
                    runs=int(runs),
                    succeeded=int(gelukt or 0),
                    partial=int(gedeeltelijk or 0),
                    failed=int(mislukt or 0),
                    items_processed=None if items is None else int(items),
                    llm_cost_eur=_float_of_none(kosten),
                    avg_duration_seconds=_float_of_none(duur),
                    assumption=aanname,
                    estimated=(
                        None
                        if aanname is None
                        else schat_besparing(
                            int(items_voor_schatting or 0),
                            aanname.manual_minutes_per_item,
                            aanname.hourly_rate_eur,
                        )
                    ),
                )
            )

        met_aanname = [p.estimated for p in packs if p.estimated is not None]
        totaal_items = [p.items_processed for p in packs if p.items_processed is not None]
        totaal_kosten = [p.llm_cost_eur for p in packs if p.llm_cost_eur is not None]
        return ROISummary(
            tenant_id=tenant_id,
            measured=MeasuredTotals(
                runs=sum(p.runs for p in packs),
                succeeded=sum(p.succeeded for p in packs),
                failed=sum(p.failed for p in packs),
                items_processed=sum(totaal_items) if totaal_items else None,
                llm_cost_eur=sum(totaal_kosten) if totaal_kosten else None,
            ),
            packs=packs,
            estimated=(
                EstimatedOut(
                    items=sum(e.items for e in met_aanname),
                    hours_saved=sum(e.hours_saved for e in met_aanname),
                    savings_eur=sum(e.savings_eur for e in met_aanname),
                )
                if met_aanname
                else None
            ),
            packs_without_assumption=[p.pack_id for p in packs if p.assumption is None],
        )
