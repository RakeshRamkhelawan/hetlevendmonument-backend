"""Logboekketen: twee gelijktijdige regels voor een klant geven geen vals manipulatiealarm.

ADR-036 OP-110. Gemeten 2026-10-20 op `8fdb38cb` in `AuditService.log_event`
(`src/core/governance/services/audit_service.py`):

- de tijdstempel werd gezet VOOR `pg_advisory_xact_lock`, en de tijdstempel zit in de hash;
- de schrijvers ketenen aan "de laatste rij met een hash, op tijdstempel en id";
- `verify_chain` loopt de keten op tijdstempel en id.

Neemt regel A zijn tijdstempel, daarna regel B (later) en schrijft B als eerste, dan zit A
achter B in de keten maar VOOR B op tijd. De verifier loopt dan A, B en meldt manipulatie op
een volkomen gave keten.

Deze test dwingt die volgorde af (de poortsessie), en draait daarnaast twintig echte
gelijktijdige rondes. Geen migratie en geen wijziging aan wat er gehasht wordt.

Vervolg (zelfde dag, OP-110): dezelfde fout zat nog in de vier andere schrijfpaden die de
ketenhash zetten: `governance/audit.py::log_action`, `governance/cookie_consent.py::update_consent`,
`governance/dsar_service.py::_create_audit_log` en `security/security_audit_service.py::log_event`.
Elk pad heeft hier dezelfde afgedwongen-volgordetest (pad tegen zichzelf EN gemengd tegen
`AuditService.log_event`), twintig gemengde rondes en de toets op een bestaande keten.

Tweede vervolg (2026-10-22, OP-110): het zesde bestand, `governance/ai_transparency_service.py`,
zette de tijdstempel op drie plekken in de AANROEPER (`log_ai_decision`,
`request_human_review`, `set_profiling_opt_out`) en liet `_populate_hash_chain` daarna het slot
nemen. Die drie aanroepers staan hier als drie extra paden in `PADEN`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.governance.audit import AuditService as ActieLogger
from src.core.governance.ai_transparency_service import AITransparencyService, ProfilingType
from src.core.governance.audit_chain_key import mark_entry
from src.core.governance.cookie_consent import CookieConsentManager
from src.core.governance.dsar_service import DSARService
from src.core.governance.hash_chain import HashChainVerifier
from src.core.governance.models import (
    AIDecision,
    AuditLog,
    HumanReviewRequest,
    UserConsent,
    UserProfilingOptOut,
)
from src.core.governance.services.audit_service import AuditService
from src.core.security.security_audit_service import SecurityAuditService
from src.core.security.types import SecurityEventType, ThreatLevel

# Eigen klantnummers: raken geen tenant van een andere test. `audit_logs` heeft geen vreemde
# sleutel naar `tenants` (migratie 20261012_audit_geen_tenant_fk), dus een kale klant volstaat.
TENANT_POORT = 910_011
TENANT_RONDES = 910_012
TENANT_BESTAAND = 910_013
# Een eigen klant per (pad, soort test): geen test raakt een andere, ook niet bij een afgebroken run.
TENANT_PAD_BASIS = 910_100
HERHALINGEN = 20

#: Het slot dat de poortsessie vasthoudt, herkend aan zijn SQL-tekst en niet aan "de eerste
#: execute": `update_consent` doet voor het slot nog een select en een commit.
SLOT_TEKST = "pg_advisory_xact_lock"


class _PoortSessie:
    """Houdt de EERSTE `execute` (het slot) vast tot de test hem openzet.

    Alles anders gaat ongewijzigd naar de echte sessie. Zo staat regel A stil op de plek waar
    de fout zit: na het kiezen van zijn tijdstempel (oude code) en vlak voor het slot.
    Het slot wordt aan zijn SQL-tekst herkend, zodat dit voor elk schrijfpad werkt, ook als het
    pad voor het slot al andere opdrachten doet.
    """

    def __init__(self, sessie: AsyncSession) -> None:
        self._sessie = sessie
        self.aangekomen = asyncio.Event()
        self.open = asyncio.Event()
        self._gepasseerd = False

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        if not self._gepasseerd and args and SLOT_TEKST in str(args[0]):
            self._gepasseerd = True
            self.aangekomen.set()
            await self.open.wait()
        return await self._sessie.execute(*args, **kwargs)

    def __getattr__(self, naam: str) -> Any:
        return getattr(self._sessie, naam)


@pytest.fixture
def sessiefabriek(postgres_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Elke schrijver een EIGEN sessie: anders serialiseert SQLAlchemy en bewijst de test niets."""
    return async_sessionmaker(bind=postgres_engine, class_=AsyncSession, expire_on_commit=False)


async def _wis(fabriek: async_sessionmaker[AsyncSession], *tenants: int) -> None:
    async with fabriek() as sessie:
        await sessie.execute(delete(AuditLog).where(AuditLog.tenant_id.in_(tenants)))
        await sessie.execute(delete(UserConsent).where(UserConsent.tenant_id.in_(tenants)))
        # De drie paden van ai_transparency_service laten ook eigen rijen achter. Eerst de
        # beoordelingsverzoeken (die wijzen naar een beslissing), dan de beslissingen.
        beslissingen = select(AIDecision.id).where(AIDecision.tenant_id.in_(tenants))
        await sessie.execute(
            delete(HumanReviewRequest).where(HumanReviewRequest.decision_id.in_(beslissingen))
        )
        await sessie.execute(delete(AIDecision).where(AIDecision.tenant_id.in_(tenants)))
        await sessie.execute(
            delete(UserProfilingOptOut).where(UserProfilingOptOut.tenant_id.in_(tenants))
        )
        await sessie.commit()


@pytest_asyncio.fixture
async def schone_klanten(
    sessiefabriek: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[None, None]:
    alle = (TENANT_POORT, TENANT_RONDES, TENANT_BESTAAND, *_PAD_TENANTS)
    await _wis(sessiefabriek, *alle)
    yield
    await _wis(sessiefabriek, *alle)


async def _schrijf(sessie: Any, tenant_id: int, naam: str) -> None:
    """Een auditregel zoals de applicatie hem schrijft, met commit door de aanroeper."""
    gelukt = await AuditService.log_event(
        db=sessie,
        event_type="logboekketen_test",
        severity="low",
        source_ip="203.0.113.10",
        endpoint="/test/logboekketen",
        description=f"regel {naam}",
        tenant_id=tenant_id,
        action="logboekketen_test",
        resource=naam,
    )
    assert gelukt, f"log_event gaf False voor {naam}"
    await sessie.commit()


async def _schrijf_log_action(sessie: Any, tenant_id: int, naam: str) -> None:
    """`governance/audit.py::log_action`: voegt toe aan de sessie, de aanroeper commit."""
    regel = await ActieLogger.log_action(
        tenant_id=tenant_id,
        action="logboekketen_test",
        resource=naam,
        details={"regel": naam},
        session=sessie,
        description=f"regel {naam}",
    )
    assert regel is not None, f"log_action gaf None voor {naam}"
    await sessie.commit()


async def _schrijf_toestemming(sessie: Any, tenant_id: int, naam: str) -> None:
    """`cookie_consent.py::update_consent`: commit zelf en slikt een mislukte auditregel in."""
    await CookieConsentManager(sessie).update_consent(
        user_id=f"logboekketen-{naam}",
        tenant_id=tenant_id,
        preferences={"analytics": True},
        policy_version="1.0",
    )


async def _schrijf_dsar(sessie: Any, tenant_id: int, naam: str) -> None:
    """`dsar_service.py::_create_audit_log`: commit zelf, best-effort."""
    await DSARService(sessie)._create_audit_log(
        tenant_id=tenant_id,
        user_id=None,
        action="logboekketen_test",
        resource=naam,
        details={"regel": naam},
        threat_level="info",
        endpoint="/test/logboekketen",
        description=f"regel {naam}",
        event_metadata={},
    )


async def _schrijf_beveiliging(sessie: Any, tenant_id: int, naam: str) -> None:
    """`security_audit_service.py::log_event`: commit zelf, best-effort."""
    gelukt = await SecurityAuditService().log_event(
        db=sessie,
        event_type=SecurityEventType.LOGOUT,
        severity=ThreatLevel.LOW,
        source_ip="203.0.113.10",
        endpoint="/test/logboekketen",
        description=f"regel {naam}",
        tenant_id=tenant_id,
        resource=naam,
        action="logboekketen_test",
    )
    assert gelukt is not None, f"SecurityAuditService.log_event gaf None voor {naam}"


async def _schrijf_ai_beslissing(sessie: Any, tenant_id: int, naam: str) -> None:
    """`ai_transparency_service.py::log_ai_decision`: commit zelf, best-effort.

    `profiling_involved=False`: anders vraagt het pad eerst de bezwaarlijst op, en dat eist op
    PostgreSQL een tenantcontext die deze test niet heeft en niet nodig heeft.
    """
    await AITransparencyService(sessie).log_ai_decision(
        user_id=f"logboekketen-{naam}",
        tenant_id=tenant_id,
        agent_id="agent_logboekketen",
        decision_type="logboekketen_test",
        explanation=f"Uitleg bij regel {naam} voor de logboekketentest",
        profiling_involved=False,
    )


async def _schrijf_ai_beoordeling(sessie: Any, tenant_id: int, naam: str) -> None:
    """`ai_transparency_service.py::request_human_review`: commit zelf, best-effort.

    Dit pad haalt de klant uit de beslissing waar het verzoek naar wijst. Zonder echte beslissing
    is die klant 0 en schrijft het pad geen ketenregel. Daarom maakt dit eerst een beslissing
    voor `tenant_id`.
    """
    beslissing = AIDecision(
        user_id=f"logboekketen-{naam}",
        tenant_id=tenant_id,
        agent_id="agent_logboekketen",
        decision_type="logboekketen_test",
        explanation=f"Uitleg bij regel {naam} voor de logboekketentest",
        profiling_involved=False,
        human_review_available=True,
        human_review_requested=False,
    )
    sessie.add(beslissing)
    await sessie.commit()
    await sessie.refresh(beslissing)
    await AITransparencyService(sessie).request_human_review(
        decision_id=str(beslissing.id),
        user_id=f"logboekketen-{naam}",
        reason=f"reden bij regel {naam}",
    )


async def _schrijf_ai_bezwaar(sessie: Any, tenant_id: int, naam: str) -> None:
    """`ai_transparency_service.py::set_profiling_opt_out`: commit zelf, best-effort."""
    await AITransparencyService(sessie).set_profiling_opt_out(
        user_id=f"logboekketen-{naam}",
        tenant_id=tenant_id,
        profiling_type=ProfilingType.BEHAVIORAL,
        opt_out=True,
    )


Schrijver = Callable[[Any, int, str], Awaitable[None]]

#: De paden uit OP-110 die nog open stonden: vier sinds de eerste vervolgdag, de drie van
#: `ai_transparency_service.py` sinds 2026-10-22. `AuditService.log_event` is het vijfde pad van
#: het eerste uur, al gefixt, en dient hier als de "andere" schrijver voor de gemengde tests.
PADEN: dict[str, Schrijver] = {
    "log_action": _schrijf_log_action,
    "update_consent": _schrijf_toestemming,
    "dsar_create_audit_log": _schrijf_dsar,
    "security_log_event": _schrijf_beveiliging,
    "ai_log_ai_decision": _schrijf_ai_beslissing,
    "ai_request_human_review": _schrijf_ai_beoordeling,
    "ai_set_profiling_opt_out": _schrijf_ai_bezwaar,
}
_PAD_NAMEN = tuple(PADEN)
_PAD_TENANTS = tuple(TENANT_PAD_BASIS + i for i in range(len(PADEN) * 4))


def _tenant_voor(pad: str, soort: int) -> int:
    """Eigen klantnummer per pad en soort test (0 zelf, 1 gemengd, 2 rondes, 3 bestaand)."""
    return TENANT_PAD_BASIS + _PAD_NAMEN.index(pad) * 4 + soort


async def _controleer(
    fabriek: async_sessionmaker[AsyncSession], tenant_id: int
) -> tuple[bool, bool, int, int]:
    async with fabriek() as sessie:
        uitslag = await HashChainVerifier(db_session=sessie).verify_chain(tenant_id)
    return (
        uitslag.is_valid,
        uitslag.tampering_detected,
        uitslag.total_entries,
        uitslag.verified_entries,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_regel_met_eerdere_tijdstempel_die_later_wordt_geketend_geeft_geen_vals_alarm(
    sessiefabriek: async_sessionmaker[AsyncSession], schone_klanten: None
) -> None:
    """A kiest zijn tijdstempel eerst, B schrijft als eerste, A volgt daarna: keten blijft gaaf."""
    async with sessiefabriek() as sessie_a, sessiefabriek() as sessie_b:
        poort = _PoortSessie(sessie_a)
        taak_a = asyncio.create_task(_schrijf(poort, TENANT_POORT, "a"))
        await asyncio.wait_for(poort.aangekomen.wait(), timeout=10)
        # B moet aantoonbaar LATER beginnen dan A bij zijn tijdstempel.
        await asyncio.sleep(0.05)
        await _schrijf(sessie_b, TENANT_POORT, "b")
        poort.open.set()
        await asyncio.wait_for(taak_a, timeout=10)

    is_valid, gemanipuleerd, totaal, geverifieerd = await _controleer(sessiefabriek, TENANT_POORT)
    assert totaal == 2
    assert not gemanipuleerd, "vals manipulatiealarm op een gave keten (OP-110)"
    assert is_valid
    assert geverifieerd == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_gelijktijdige_regels_voor_een_klant_houden_de_keten_gaaf_twintig_keer(
    sessiefabriek: async_sessionmaker[AsyncSession], schone_klanten: None
) -> None:
    """Echte gelijktijdigheid, eigen sessie per regel, twintig herhalingen met elk twee regels."""

    async def _een(naam: str) -> None:
        async with sessiefabriek() as sessie:
            await _schrijf(sessie, TENANT_RONDES, naam)

    for ronde in range(HERHALINGEN):
        await asyncio.gather(_een(f"r{ronde}a"), _een(f"r{ronde}b"))
        is_valid, gemanipuleerd, totaal, geverifieerd = await _controleer(
            sessiefabriek, TENANT_RONDES
        )
        assert totaal == 2 * (ronde + 1)
        assert not gemanipuleerd, f"vals manipulatiealarm in ronde {ronde} (OP-110)"
        assert is_valid, f"keten ongeldig in ronde {ronde}"
        assert geverifieerd == totaal


@pytest.mark.integration
@pytest.mark.asyncio
async def test_een_bestaande_keten_van_voor_de_fix_blijft_geldig(
    sessiefabriek: async_sessionmaker[AsyncSession], schone_klanten: None
) -> None:
    """Rijen zoals de OUDE schrijver ze maakte (tijdstempel eerst vastgelegd, dagen uit elkaar).

    Ze worden hier zonder `log_event` gebouwd, met dezelfde `_compute_hash` en `mark_entry`
    als de schrijvers, zodat de fix er niet in kan zitten. Daarna schrijft de NIEUWE code er
    nog twee achter: de hele keten moet gaaf blijven.
    """
    begin = datetime.now(timezone.utc) - timedelta(days=5)
    async with sessiefabriek() as sessie:
        verifier = HashChainVerifier(db_session=sessie)
        vorige: str | None = None
        for i in range(5):
            rij = AuditLog(
                tenant_id=TENANT_BESTAAND,
                timestamp=begin + timedelta(days=i),
                event_type="logboekketen_test",
                threat_level="low",
                client_ip="203.0.113.10",
                endpoint="/test/logboekketen",
                description=f"oud {i}",
                action="logboekketen_test",
                resource=f"oud{i}",
                event_metadata={},
                details={},
            )
            rij.previous_hash = vorige
            mark_entry(rij)
            rij.audit_hash = verifier._compute_hash(rij, vorige)
            vorige = rij.audit_hash
            sessie.add(rij)
        await sessie.commit()

    uitslag = await _controleer(sessiefabriek, TENANT_BESTAAND)
    assert uitslag == (True, False, 5, 5)

    async with sessiefabriek() as sessie:
        await _schrijf(sessie, TENANT_BESTAAND, "nieuw1")
    async with sessiefabriek() as sessie:
        await _schrijf(sessie, TENANT_BESTAAND, "nieuw2")

    uitslag = await _controleer(sessiefabriek, TENANT_BESTAAND)
    assert uitslag == (True, False, 7, 7)

    # De nieuwe rijen staan op tijd ACHTER de oude: de tijdstempel loopt mee met de keten.
    async with sessiefabriek() as sessie:
        tijden = list(
            (
                await sessie.execute(
                    select(AuditLog.timestamp)
                    .where(AuditLog.tenant_id == TENANT_BESTAAND)
                    .order_by(AuditLog.id.asc())
                )
            )
            .scalars()
            .all()
        )
    assert tijden == sorted(tijden)


async def _afgedwongen_volgorde(
    fabriek: async_sessionmaker[AsyncSession],
    tenant_id: int,
    schrijver_a: Schrijver,
    schrijver_b: Schrijver,
) -> tuple[bool, bool, int, int]:
    """A bereikt het slot eerst, B schrijft helemaal weg, daarna gaat A verder."""
    async with fabriek() as sessie_a, fabriek() as sessie_b:
        poort = _PoortSessie(sessie_a)
        taak_a = asyncio.create_task(schrijver_a(poort, tenant_id, "a"))
        await asyncio.wait_for(poort.aangekomen.wait(), timeout=10)
        # B moet aantoonbaar LATER beginnen dan A bij zijn tijdstempel.
        await asyncio.sleep(0.05)
        await schrijver_b(sessie_b, tenant_id, "b")
        poort.open.set()
        await asyncio.wait_for(taak_a, timeout=10)
    return await _controleer(fabriek, tenant_id)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("pad", _PAD_NAMEN)
async def test_elk_schrijfpad_geeft_bij_afgedwongen_volgorde_geen_vals_alarm(
    sessiefabriek: async_sessionmaker[AsyncSession], schone_klanten: None, pad: str
) -> None:
    """Pad tegen zichzelf: A kiest eerst, B schrijft als eerste, A volgt: keten blijft gaaf."""
    is_valid, gemanipuleerd, totaal, geverifieerd = await _afgedwongen_volgorde(
        sessiefabriek, _tenant_voor(pad, 0), PADEN[pad], PADEN[pad]
    )
    assert totaal == 2, f"{pad}: verwacht twee regels, kreeg {totaal} (fout ingeslikt?)"
    assert not gemanipuleerd, f"{pad}: vals manipulatiealarm op een gave keten (OP-110)"
    assert is_valid
    assert geverifieerd == 2


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("pad", _PAD_NAMEN)
async def test_elk_schrijfpad_gemengd_met_audit_service_log_event_geeft_geen_vals_alarm(
    sessiefabriek: async_sessionmaker[AsyncSession], schone_klanten: None, pad: str
) -> None:
    """Gemengd: A via dit pad (gepauzeerd bij het slot), B via `AuditService.log_event`."""
    is_valid, gemanipuleerd, totaal, geverifieerd = await _afgedwongen_volgorde(
        sessiefabriek, _tenant_voor(pad, 1), PADEN[pad], _schrijf
    )
    assert totaal == 2, f"{pad}: verwacht twee regels, kreeg {totaal} (fout ingeslikt?)"
    assert not gemanipuleerd, f"{pad} tegen log_event: vals manipulatiealarm (OP-110)"
    assert is_valid
    assert geverifieerd == 2


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("pad", _PAD_NAMEN)
async def test_gemengde_gelijktijdige_regels_houden_de_keten_gaaf_twintig_keer(
    sessiefabriek: async_sessionmaker[AsyncSession], schone_klanten: None, pad: str
) -> None:
    """Twintig echte rondes: een regel via `AuditService.log_event` en een via dit pad.

    LET OP voor `update_consent` (opmerking Gate 2, 2026-10-21): deze twintig rondes zijn kans en
    geen bewijs. Dat pad doet voor het slot nog een select en een commit, en of twee regels
    elkaar dan precies in het venster raken is toeval (niet gemeten); groen betekent hier dus
    niet vanzelf dat de volgorde klopt. Het BEWIJS voor dat pad (en voor elk ander pad) dragen
    de afgedwongen tests hierboven:
    `test_elk_schrijfpad_geeft_bij_afgedwongen_volgorde_geen_vals_alarm` en
    `test_elk_schrijfpad_gemengd_met_audit_service_log_event_geeft_geen_vals_alarm`, die het slot
    vasthouden tot de andere regel klaar is. Deze rondes vangen alleen een regressie die ook bij
    toeval zichtbaar wordt.
    """
    tenant_id = _tenant_voor(pad, 2)

    async def _een(schrijver: Schrijver, naam: str) -> None:
        async with sessiefabriek() as sessie:
            await schrijver(sessie, tenant_id, naam)

    for ronde in range(HERHALINGEN):
        await asyncio.gather(
            _een(_schrijf, f"r{ronde}a"),
            _een(PADEN[pad], f"r{ronde}b"),
        )
        is_valid, gemanipuleerd, totaal, geverifieerd = await _controleer(sessiefabriek, tenant_id)
        assert totaal == 2 * (ronde + 1), f"{pad}: ronde {ronde}: {totaal} regels"
        assert not gemanipuleerd, f"{pad}: vals manipulatiealarm in ronde {ronde} (OP-110)"
        assert is_valid, f"{pad}: keten ongeldig in ronde {ronde}"
        assert geverifieerd == totaal


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("pad", _PAD_NAMEN)
async def test_een_bestaande_keten_van_voor_de_fix_blijft_geldig_voor_elk_schrijfpad(
    sessiefabriek: async_sessionmaker[AsyncSession], schone_klanten: None, pad: str
) -> None:
    """Oude rijen (tijdstempel eerst vastgelegd), daarna twee nieuwe via dit pad: gaaf."""
    tenant_id = _tenant_voor(pad, 3)
    begin = datetime.now(timezone.utc) - timedelta(days=5)
    async with sessiefabriek() as sessie:
        verifier = HashChainVerifier(db_session=sessie)
        vorige: str | None = None
        for i in range(5):
            rij = AuditLog(
                tenant_id=tenant_id,
                timestamp=begin + timedelta(days=i),
                event_type="logboekketen_test",
                threat_level="low",
                client_ip="203.0.113.10",
                endpoint="/test/logboekketen",
                description=f"oud {i}",
                action="logboekketen_test",
                resource=f"oud{i}",
                event_metadata={},
                details={},
            )
            rij.previous_hash = vorige
            mark_entry(rij)
            rij.audit_hash = verifier._compute_hash(rij, vorige)
            vorige = rij.audit_hash
            sessie.add(rij)
        await sessie.commit()

    assert await _controleer(sessiefabriek, tenant_id) == (True, False, 5, 5)

    for naam in ("nieuw1", "nieuw2"):
        async with sessiefabriek() as sessie:
            await PADEN[pad](sessie, tenant_id, naam)

    assert await _controleer(sessiefabriek, tenant_id) == (True, False, 7, 7), pad

    async with sessiefabriek() as sessie:
        tijden = list(
            (
                await sessie.execute(
                    select(AuditLog.timestamp)
                    .where(AuditLog.tenant_id == tenant_id)
                    .order_by(AuditLog.id.asc())
                )
            )
            .scalars()
            .all()
        )
    assert tijden == sorted(tijden), pad
