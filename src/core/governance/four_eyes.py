"""Vier ogen: moet een ANDER dan de aanvrager deze actie beslissen? (ADR-039, besluit Rakesh 2026-10-04).

Mens-in-de-lus staat altijd aan bij een riskante agentactie. Of de aanvrager zijn eigen verzoek
mag beslissen, is een instelling van de tenant zelf, per actie. Standaard UIT: wie het nooit
heeft aangezet, werkt als een zzp'er -- er is geen tweede paar ogen.

**Waarom `tenants.settings` en geen eigen tabel.** De kolom bestaat al (JSON, per tenant) en
heeft geen migratie nodig. De sleutel `four_eyes_actions` is een lijst toolnamen. Pas als vier
ogen per workflow of per bedrag wordt ingesteld, is een eigen tabel de betere plek; dat is niet
vandaag (ADR-039, "Waar beginnen we").
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import (
    DEFAULT_FOUR_EYES_ACTIONS,
    FOUR_EYES_EXPLANATION_PENDING_KEY,
    FOUR_EYES_MIGRATION_MARK_KEY,
    FOUR_EYES_SETTINGS_KEY,
    with_four_eyes_defaults,
)

__all__ = ["FOUR_EYES_SETTINGS_KEY", "with_four_eyes_defaults"]


@dataclass(frozen=True)
class FourEyesAction:
    """Een actie waarvoor de tenant vier ogen kan instellen."""

    name: str
    label: str
    group: str
    default_on: bool
    #: False voor een gereserveerde naam: de tool bestaat nog niet, maar de standaard staat al
    #: klaar zodat hij klopt op de dag dat de tool er komt.
    available: bool


#: De acties die de tenant kan instellen, met de standaard uit ADR-039 ("Standaardinstelling
#: vier ogen", Rakesh 2026-10-05): AAN voor HR (Annex III), betalingen, IBAN wijzigen, afboeken
#: en overdracht aan incasso; UIT voor herinneringen en aanmaningen. De HR-namen zijn de drie
#: tools van de HR-skills (`src/core/config/tool_risk_levels.yml`); de vier geldnamen zijn
#: gereserveerd.
FOUR_EYES_ACTIONS: tuple[FourEyesAction, ...] = (
    FourEyesAction("query_hr_database", "Personeelsgegevens opvragen", "Personeel", True, True),
    FourEyesAction("analyze_skill_gap", "Vaardigheden van personeel beoordelen", "Personeel", True, True),
    FourEyesAction("schedule_training", "Training aan een medewerker toewijzen", "Personeel", True, True),
    FourEyesAction("make_payment", "Een betaling doen", "Geld", True, False),
    FourEyesAction("change_iban", "Een IBAN wijzigen", "Geld", True, False),
    FourEyesAction("write_off_receivable", "Een factuur afboeken", "Geld", True, False),
    FourEyesAction(
        "transfer_to_debt_collection", "Een factuur overdragen aan incasso", "Geld", True, False
    ),
    FourEyesAction(
        "send_payment_reminder", "Een herinnering of aanmaning versturen", "Debiteuren", False, True
    ),
    FourEyesAction(
        "propose_payment_run",
        "Een betaalvoorstel van de crediteurenagent goedkeuren",
        "Crediteuren",
        False,
        True,
    ),
    FourEyesAction(
        "propose_supplier_invoice",
        "Een inkoopfactuur vastleggen die de crediteurenagent voorlegt",
        "Crediteuren",
        False,
        True,
    ),
)

FOUR_EYES_ACTION_NAMES = frozenset(a.name for a in FOUR_EYES_ACTIONS)


def default_four_eyes_actions() -> list[str]:
    """De acties die in een NIEUWE omgeving standaard vier ogen hebben."""
    return list(DEFAULT_FOUR_EYES_ACTIONS)


def four_eyes_from_settings(settings: object, action: str) -> bool:
    """De zuivere regel: staat vier ogen aan voor deze actie?

    - geen instellingen, of geen sleutel: UIT (de standaard uit ADR-039);
    - een lijst: AAN als de actie erin staat;
    - de sleutel staat er maar is geen lijst: AAN. Iemand heeft iets ingesteld en het is niet te
      lezen; dan valt de regel dicht in plaats van stil open.
    """
    if not isinstance(settings, dict) or FOUR_EYES_SETTINGS_KEY not in settings:
        return False
    acties = settings[FOUR_EYES_SETTINGS_KEY]
    if not isinstance(acties, list):
        return True
    return action in acties


async def read_four_eyes_actions(db: AsyncSession, *, tenant_id: int) -> list[dict[str, object]]:
    """Per actie uit de catalogus: naam, Nederlandse omschrijving, groep, en of vier ogen aan staat.

    Gelezen met dezelfde regel als de goedkeurcontrole (`four_eyes_from_settings`), zodat het
    scherm nooit iets anders toont dan wat er bij goedkeuren werkelijk geldt.
    """
    from src.core.models.rbac_models import Tenant

    result = await db.execute(select(Tenant.settings).where(Tenant.id == tenant_id))
    settings = result.scalar_one_or_none()
    return [
        {
            "name": a.name,
            "label": a.label,
            "group": a.group,
            "available": a.available,
            "default_on": a.default_on,
            "enabled": four_eyes_from_settings(settings, a.name),
        }
        for a in FOUR_EYES_ACTIONS
    ]


async def write_four_eyes_actions(
    db: AsyncSession, *, tenant_id: int, actions: list[str]
) -> tuple[list[str], list[str]]:
    """Zet de lijst acties met vier ogen AAN voor DEZE tenant. Geeft (oud, nieuw).

    Alleen namen uit de catalogus (`ValueError` anders). De rest van `settings` blijft staan.
    Commit zelf. Een nieuw dict toewijzen en niet in-place wijzigen: een JSON-kolom ziet een
    mutatie binnen het object niet als wijziging.
    """
    from src.core.models.rbac_models import Tenant

    onbekend = sorted(set(actions) - FOUR_EYES_ACTION_NAMES)
    if onbekend:
        raise ValueError(f"onbekende acties: {', '.join(onbekend)}")
    # Met rijslot en verse rij: de hele JSON wordt teruggeschreven, dus een oude kopie overschrijft de wijziging van een
    # ander (bijvoorbeeld de escalatietermijn) -- Gate 2 ronde 2.
    tenant = (
        await db.execute(
            select(Tenant)
            .where(Tenant.id == tenant_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if tenant is None:
        raise LookupError("tenant bestaat niet")
    huidig = tenant.settings if isinstance(tenant.settings, dict) else {}
    oud_raw = huidig.get(FOUR_EYES_SETTINGS_KEY)
    oud = [str(x) for x in oud_raw] if isinstance(oud_raw, list) else []
    nieuw = [a.name for a in FOUR_EYES_ACTIONS if a.name in set(actions)]
    # Het migratiemerkteken gaat weg: vanaf nu is dit de keuze van de gebruiker, en de
    # `downgrade()` van `20261007_vier_ogen_bestaande_tenants` mag die niet terugdraaien.
    rest = {k: v for k, v in huidig.items() if k != FOUR_EYES_MIGRATION_MARK_KEY}
    tenant.settings = {**rest, FOUR_EYES_SETTINGS_KEY: nieuw}
    await db.commit()
    return oud, nieuw


async def read_explanation_pending(db: AsyncSession, *, tenant_id: int) -> bool:
    """Moet een beheerder van DEZE tenant de uitleg over vier ogen nog zien?"""
    from src.core.models.rbac_models import Tenant

    result = await db.execute(select(Tenant.settings).where(Tenant.id == tenant_id))
    settings = result.scalar_one_or_none()
    return isinstance(settings, dict) and settings.get(FOUR_EYES_EXPLANATION_PENDING_KEY) is True


async def confirm_four_eyes_explanation(db: AsyncSession, *, tenant_id: int) -> bool:
    """Haal de uitlegmarkering weg voor DEZE tenant. Geeft terug of hij er stond. Commit zelf.

    Alleen die ene sleutel; de vier-ogen-instelling zelf en het migratiemerkteken blijven staan.
    """
    from src.core.models.rbac_models import Tenant

    # Met rijslot en verse rij: de hele JSON wordt teruggeschreven, dus een oude kopie overschrijft de wijziging van een
    # ander (bijvoorbeeld de escalatietermijn) -- Gate 2 ronde 2.
    tenant = (
        await db.execute(
            select(Tenant)
            .where(Tenant.id == tenant_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if tenant is None:
        raise LookupError("tenant bestaat niet")
    huidig = tenant.settings if isinstance(tenant.settings, dict) else {}
    if FOUR_EYES_EXPLANATION_PENDING_KEY not in huidig:
        return False
    tenant.settings = {k: v for k, v in huidig.items() if k != FOUR_EYES_EXPLANATION_PENDING_KEY}
    await db.commit()
    return True


async def is_four_eyes_required(db: AsyncSession, *, tenant_id: int, action: str) -> bool:
    """Lees de instelling van DEZE tenant. Een fout bij het lezen gaat omhoog, niet naar UIT."""
    from src.core.models.rbac_models import Tenant

    result = await db.execute(select(Tenant.settings).where(Tenant.id == tenant_id))
    return four_eyes_from_settings(result.scalar_one_or_none(), action)
