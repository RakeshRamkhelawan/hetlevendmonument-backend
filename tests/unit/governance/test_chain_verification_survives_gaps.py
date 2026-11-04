"""Een ongehashte rij is een GAT, geen manipulatie (ADR-036 OP-108).

**De bevinding.** `governance/retention_cleanup.py` en `copilot/api/contest_service.py` schrijven
auditregels met rauwe SQL, zonder `audit_hash` EN zonder `previous_hash`. De opruimactor draait
dagelijks voor elke tenant, dus elke omgeving heeft zulke rijen.

De zes schrijvers ketenen bewust aan de laatste rij MET een hash:

    .where(AuditLog.tenant_id == ..., AuditLog.audit_hash.isnot(None))
    .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())

De verificatie deed dat NIET, en brak daarom in twee vormen -- allebei gedekt door de tests
hieronder, want de eerste is de vorm die in de praktijk optreedt en die stond aanvankelijk fout
in ADR-036:

1. **Gat in het midden.** De ongehashte rij heeft ook `previous_hash = NULL`. De link-controle
   vergelijkt dat met de hash van de vorige rij en breekt OP DE GAT-RIJ ZELF.
2. **Gat op de eerste rij van het venster.** Dan wordt de link-controle overgeslagen en zet
   `previous_hash = stored_hash or computed_hash` een VERZONNEN basislijn, waarna de volgende,
   onschuldige rij omvalt.

In beide gevallen zorgde `break` dat alles daarna nooit meer werd bekeken -- inclusief het
art.-14-bewijs uit H-2.

**Waarom `is_valid` toch False blijft bij een gat.** Na deze fix is een rij met
`audit_hash IS NULL` niet te onderscheiden van een rij waarvan een aanvaller de hash heeft
LEEGGEMAAKT na een inhoudswijziging. Gaten negeren zou hash-strippen tot een stille
manipulatieroute maken. Het gat telt dus mee in het oordeel, maar wordt APART geteld
(`unhashed_entries`) zodat het te onderscheiden is van echte manipulatie (`tampering_detected`).

**Mutatietest (2026-08-10, beide richtingen):** de `break` teruggezet -> ROOD op
`test_real_tampering_after_a_gap_is_still_caught`. `previous_hash = stored_hash or computed_hash`
teruggezet -> ROOD op beide gat-tests. Een keten zonder gaten -> blijft GROEN.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.hash_chain import HashChainVerifier
from src.core.governance.models import AuditLog

_T0 = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)


def _verifier(entries: list[AuditLog]) -> HashChainVerifier:
    """Een verifier die exact deze rijen teruggeeft, op tijdstempel gesorteerd."""
    sessie = AsyncMock(spec=AsyncSession)
    resultaat = Mock()
    resultaat.scalars = Mock(return_value=Mock(all=Mock(return_value=entries)))
    sessie.execute = AsyncMock(return_value=resultaat)
    return HashChainVerifier(db_session=sessie)


def _rij(index: int, *, tenant_id: int = 1) -> AuditLog:
    return AuditLog(
        id=index,
        tenant_id=tenant_id,
        action=f"actie_{index}",
        resource=f"bron_{index}",
        timestamp=_T0 + timedelta(minutes=index),
    )


def _ketting(lengte: int, *, gat_op: int | None = None) -> list[AuditLog]:
    """Een correcte keten, eventueel met een ONGEHASHTE rij op positie `gat_op`.

    Het gat wordt gebouwd zoals de rauwe schrijvers het doen: `audit_hash` EN `previous_hash`
    allebei NULL. Dat is het verschil met een verzonnen testrij, en precies waar de eerste
    diagnose in ADR-036 op misging.
    """
    verifier = HashChainVerifier(db_session=None)
    rijen: list[AuditLog] = []
    vorige: str | None = None
    for i in range(lengte):
        rij = _rij(i)
        if i == gat_op:
            rij.audit_hash = None
            rij.previous_hash = None
            rijen.append(rij)
            continue  # de keten loopt DOOR over het gat heen -- zo doen de schrijvers het
        rij.previous_hash = vorige
        rij.audit_hash = verifier._compute_hash(rij, vorige)
        vorige = rij.audit_hash
        rijen.append(rij)
    return rijen


@pytest.mark.asyncio
class TestAGapIsNotTampering:
    async def test_an_intact_chain_is_valid(self):
        """Vangnet: zonder deze toets zou 'meld nooit iets' een geldige oplossing zijn."""
        resultaat = await _verifier(_ketting(4)).verify_chain(tenant_id=1)

        assert resultaat.is_valid is True
        assert resultaat.verified_entries == 4
        assert resultaat.unhashed_entries == 0
        assert resultaat.tampering_detected is False

    async def test_a_gap_in_the_middle_is_reported_as_a_gap(self):
        """Vorm 1 -- de vorm die in elke omgeving voorkomt.

        Voor de fix brak de link-controle OP de gat-rij en werd die als manipulatie gemeld.
        """
        resultaat = await _verifier(_ketting(4, gat_op=1)).verify_chain(tenant_id=1)

        assert resultaat.unhashed_entries == 1, (
            "Het gat wordt niet als gat geteld. Dan is een ongehashte rij niet te onderscheiden "
            "van manipulatie (ADR-036 OP-108)."
        )
        assert resultaat.tampering_detected is False, (
            "Een ongehashte rij wordt als MANIPULATIE gemeld. Dat is onwaar en het stuurt een "
            "P0-incidentprocedure aan voor een bekende, geregistreerde bevinding."
        )
        assert resultaat.verified_entries == 3, (
            "De rijen NA het gat zijn niet geverifieerd. Dat is de kern van OP-108: de "
            "verificatie kwam nooit voorbij het gat, dus ook niet bij het art.-14-bewijs."
        )
        assert resultaat.is_valid is False, (
            "Een keten met een gat mag niet als geldig gelden -- een leeggemaakte hash is niet "
            "te onderscheiden van een nooit-gehashte rij."
        )

    async def test_a_gap_on_the_first_row_does_not_poison_the_next(self):
        """Vorm 2 -- het gat staat vooraan, dus de link-controle wordt overgeslagen."""
        resultaat = await _verifier(_ketting(4, gat_op=0)).verify_chain(tenant_id=1)

        assert resultaat.unhashed_entries == 1
        assert resultaat.tampering_detected is False, (
            "De rij NA een gat-op-index-0 wordt als gemanipuleerd gemeld. Dat komt doordat de "
            "basislijn werd gevuld met een VERZONNEN hash die nooit is opgeslagen."
        )
        assert resultaat.verified_entries == 3

    async def test_real_tampering_after_a_gap_is_still_caught(self):
        """De tweede richting, en tegelijk de winst: dit KON vandaag niet.

        Door de `break` kwam de verificatie nooit voorbij het gat, dus manipulatie erna was
        onzichtbaar. Zonder deze test zou 'meld gaten en stop verder met controleren' groen zijn.
        """
        rijen = _ketting(5, gat_op=1)
        rijen[3].action = "STIEKEM_GEWIJZIGD"  # hash blijft de oude -> hercompute moet omvallen

        resultaat = await _verifier(rijen).verify_chain(tenant_id=1)

        assert resultaat.tampering_detected is True, (
            "Manipulatie NA een gat wordt niet betrapt. Dat is precies wat OP-108 onmogelijk "
            "maakte: de verificatie stopte bij het gat."
        )
        assert resultaat.is_valid is False
        assert resultaat.broken_at_entry_id == rijen[3].id, (
            "De gemanipuleerde rij wordt niet aangewezen; het oordeel is dan niet te gebruiken "
            "voor forensiek."
        )

    async def test_tampering_without_any_gap_still_works(self):
        """Regressievangnet op het pad dat vandaag al werkt."""
        rijen = _ketting(4)
        rijen[2].action = "STIEKEM_GEWIJZIGD"

        resultaat = await _verifier(rijen).verify_chain(tenant_id=1)

        assert resultaat.tampering_detected is True
        assert resultaat.unhashed_entries == 0
        assert resultaat.broken_at_entry_id == rijen[2].id


def _verifier_met_reeks(resultaten: list[object]) -> HashChainVerifier:
    """Een verifier waarvan opeenvolgende `execute()`-aanroepen deze rijen teruggeven."""
    sessie = AsyncMock(spec=AsyncSession)
    beurten = []
    for item in resultaten:
        r = Mock()
        if isinstance(item, list):
            r.scalars = Mock(return_value=Mock(all=Mock(return_value=item)))
        else:
            r.scalar_one_or_none = Mock(return_value=item)
        beurten.append(r)
    sessie.execute = AsyncMock(side_effect=beurten)
    return HashChainVerifier(db_session=sessie)


@pytest.mark.asyncio
class TestTheOtherVerifiersAgreeAboutGaps:
    """Alle verifiers moeten hetzelfde zeggen over een gat (ADR-036 OP-108).

    Zolang `verify_chain` gerepareerd is en de andere niet, spreken de endpoints elkaar tegen:
    `/integrity/verify` meldt een gat en `/integrity/status` meldt "healthy". Een halve
    reparatie is hier erger dan geen, want dan hangt het oordeel af van welk endpoint je toevallig
    bevraagt.
    """

    async def test_verify_entry_does_not_blame_the_row_after_a_gap(self):
        """`verify_entry` zoekt de vorige rij zonder `audit_hash IS NOT NULL`.

        Is de direct voorafgaande rij ongehasht, dan wordt de basislijn `None` en faalt de
        ONSCHULDIGE rij op zowel de hercompute als de link. Juist dit endpoint vraagt een auditor
        per regel op voor het art.-14-bewijs uit H-2.

        **Deze test toetst de QUERY, niet het antwoord van een mock.** Een eerdere versie gaf de
        verifier via een mock gewoon de juiste vorige rij terug en slaagde daarmee ook ZONDER de
        fix -- de mock beantwoordde de vraag die de code fout stelt. Dat is exact de faalvorm
        waar deze reeks over gaat: de test verzint zijn eigen invoer aan beide kanten.

        Daarom: de prev-lookup MOET het predicaat `audit_hash IS NOT NULL` bevatten. Toetsen op
        alleen de kolomnaam zou hol zijn -- die staat sowieso in de SELECT-lijst.
        """
        rijen = _ketting(3, gat_op=1)
        doelrij = rijen[2]
        assert rijen[1].audit_hash is None and doelrij.audit_hash is not None

        verifier = _verifier_met_reeks([doelrij, rijen[0]])
        await verifier.verify_entry(entry_id=doelrij.id, tenant_id=1)

        aanroepen = verifier.db_session.execute.await_args_list
        assert len(aanroepen) >= 2, (
            "Er is geen tweede query gedaan om de vorige rij op te halen; dan meet deze test niets."
        )
        prev_sql = str(
            aanroepen[1].args[0].compile(compile_kwargs={"literal_binds": True})
        ).replace("\n", " ")

        assert "audit_hash IS NOT NULL" in prev_sql, (
            "De prev-lookup filtert niet op `audit_hash IS NOT NULL`. Is de direct voorafgaande "
            "rij een gat, dan wordt de basislijn None en faalt de ONSCHULDIGE rij op zowel de "
            "hercompute als de link. Juist dit endpoint vraagt een auditor per regel op voor het "
            f"art.-14-bewijs uit H-2.\n\nSQL was:\n{prev_sql}"
        )
        assert "audit_logs.id DESC" in prev_sql, (
            "De prev-lookup sorteert niet op `id` als tiebreak. Bij twee rijen met dezelfde "
            "tijdstempel kiest hij dan een andere voorganger dan de SCHRIJVER deed "
            f"(ADR-036 OP-110).\n\nSQL was:\n{prev_sql}"
        )

    async def test_chain_status_counts_a_gap_once_and_not_as_broken(self):
        """`get_chain_status` telt vandaag TWEE gebroken regels per gat.

        De gat-rij zelf valt om op de link-controle, en daarna zet
        `previous_hash = stored_hash or computed_hash` een verzonnen basislijn waardoor ook de
        volgende rij omvalt. Dat maakt `health_percentage` structureel te laag en `status`
        "broken" voor een keten waarin niets is gemanipuleerd.
        """
        status = await _verifier_met_reeks([_ketting(4, gat_op=1)]).get_chain_status(tenant_id=1)

        assert status.broken_entries_count == 0, (
            f"Een gat levert {status.broken_entries_count} 'gebroken' regels op terwijl er niets "
            "is gemanipuleerd."
        )
        assert status.unhashed_entries == 1, "Het gat wordt nergens apart geteld."
        assert status.status == "unverified", (
            f"Status is {status.status!r}. Een keten met een gat is niet 'healthy' -- dan zou "
            "`/integrity/status` het tegenovergestelde zeggen van `/integrity/verify` -- en ook "
            "niet 'broken', want er is geen manipulatie."
        )

    async def test_chain_status_still_reports_real_tampering(self):
        """De tweede richting: zonder dit zou 'tel nooit iets als gebroken' groen zijn."""
        rijen = _ketting(4, gat_op=1)
        rijen[3].action = "STIEKEM_GEWIJZIGD"

        status = await _verifier_met_reeks([rijen]).get_chain_status(tenant_id=1)

        assert status.broken_entries_count >= 1
        assert status.status != "healthy"


@pytest.mark.asyncio
class TestTheFourthVerifierAndTheDateWindow:
    """Wat de blinde ronde van 2026-08-10 vond, nadat ik "alle vier" had geclaimd.

    Drie onafhankelijke reviewers kwamen op dezelfde punten uit. Twee daarvan waren onjuiste
    beweringen van MIJ:

    1. `verify_log_integrity` had als enige de `id`-tiebreak NIET gekregen, terwijl de
       commitboodschap "alle vier verifiers volgen nu dezelfde regel als de schrijvers" claimde.
       Gemeten door een reviewer: vijf valse manipulatiemeldingen op een ONGESCHONDEN keten van
       drie met gelijke tijdstempels.
    2. Er was helemaal geen test voor het gat-pad van die vierde verifier.

    En een nieuw gat dat door mijn eigen wijziging ERGER werd: bij een datumvenster begint de
    traversal met een lege basislijn, terwijl de eerste rij in het venster een echte
    `previous_hash` naar buiten het venster heeft. Dat gaf altijd al een breuk, maar sinds
    `tampering_detected` in `schemas.py` is gedocumenteerd als "the P0 signal" is het een VALS
    P0-alarm op een gave keten -- op precies de vraag die een auditor stelt.
    """

    async def test_verify_log_integrity_skips_a_gap_without_blaming_anyone(self):
        """De vierde verifier moet dezelfde regel volgen als de andere drie."""
        from src.core.security.security_audit_service import SecurityAuditService

        dienst = SecurityAuditService()
        rijen = _ketting(4, gat_op=1)
        sessie = AsyncMock(spec=AsyncSession)
        # Sinds ADR-036 OP-122 doet deze verifier TWEE queries: eerst het venster (nu
        # `ORDER BY timestamp DESC`, dus de database levert nieuwste-eerst) en daarna de
        # basislijn-lookup naar de rij ervoor. De mock moet dat modelleren, anders krijgt de
        # basislijn een Mock in plaats van een hash en meldt de eerste rij een valse breuk.
        venster = Mock()
        venster.scalars = Mock(return_value=Mock(all=Mock(return_value=list(reversed(rijen)))))
        basislijn = Mock()
        basislijn.scalar_one_or_none = Mock(return_value=None)
        sessie.execute = AsyncMock(side_effect=[venster, basislijn])

        uitkomst = await dienst.verify_log_integrity(db=sessie, tenant_id=1)

        assert uitkomst["tampered_entries"] == [], (
            f"Een gat levert manipulatiemeldingen op: {uitkomst['tampered_entries']}. De vierde "
            "verifier volgt de skip-regel niet die de andere drie wel hebben."
        )
        assert uitkomst["unhashed_entries"] == 1
        assert uitkomst["tampering_detected"] is False
        assert uitkomst["verified"] is False, "Een gat hoort wel in het oordeel mee te tellen."

    async def test_verify_log_integrity_orders_by_id_as_tiebreak(self):
        """Toetst de QUERY, want bij gelijke tijdstempels beslist de database anders dan wij.

        Zonder `id` als tiebreak loopt deze verifier in een andere volgorde dan waarin de
        SCHRIJVERS hebben geketend (die gebruiken `timestamp DESC, id DESC`). Gemeten door een
        blinde reviewer: vijf valse meldingen op een schone keten van drie.
        """
        from src.core.security.security_audit_service import SecurityAuditService

        dienst = SecurityAuditService()
        sessie = AsyncMock(spec=AsyncSession)
        resultaat = Mock()
        resultaat.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
        sessie.execute = AsyncMock(return_value=resultaat)

        await dienst.verify_log_integrity(db=sessie, tenant_id=1)

        sql = str(
            sessie.execute.await_args_list[0].args[0].compile(
                compile_kwargs={"literal_binds": True}
            )
        ).replace("\n", " ")
        assert "audit_logs.id ASC" in sql or "audit_logs.id" in sql.split("ORDER BY")[-1], (
            f"De volgorde heeft geen `id` als tiebreak (ADR-036 OP-110).\n\nSQL was:\n{sql}"
        )

    async def test_a_date_window_does_not_report_a_clean_chain_as_tampered(self):
        """Een periode-rapport mag geen VALS P0-signaal geven.

        De eerste rij in het venster heeft een echte `previous_hash` naar een rij ERBUITEN. Start
        de traversal met een lege basislijn, dan wijkt de hercompute af en heet dat manipulatie.
        """
        rijen = _ketting(6)
        venster = rijen[3:]  # de database geeft alleen het venster terug
        vanaf = venster[0].timestamp
        # Twee queries: eerst het venster, dan de basislijn-lookup naar de rij ERVOOR.
        verifier = _verifier_met_reeks([venster, rijen[2].audit_hash])

        resultaat = await verifier.verify_chain(tenant_id=1, start_date=vanaf)

        assert resultaat.tampering_detected is False, (
            "Een gave keten wordt binnen een datumvenster als GEMANIPULEERD gemeld. Dat veld is "
            "in schemas.py gedocumenteerd als 'the P0 signal'; wie dit een keer ziet gelooft het "
            "signaal daarna nooit meer."
        )
        assert resultaat.is_valid is True

    async def test_verify_entry_on_a_gap_row_does_not_claim_a_hash_mismatch(self):
        """Een gat-rij is niet na te rekenen -- dat is iets anders dan "de hash klopt niet".

        Voor deze fix gaf `verify_entry` op een ongehashte rij `stored_hash=""`, dus
        `hash_matches=False`: ononderscheidbaar van manipulatie. Op precies het endpoint waarop
        een auditor per regel het art.-14-bewijs opvraagt.
        """
        rijen = _ketting(3, gat_op=1)
        gatrij = rijen[1]
        verifier = _verifier_met_reeks([gatrij, rijen[0]])

        resultaat = await verifier.verify_entry(entry_id=gatrij.id, tenant_id=1)

        assert resultaat.is_valid is False, (
            "Een ongehashte rij is niet na te rekenen; die mag niet als geldig gelden."
        )
        assert resultaat.previous_hash_matches is True, (
            "Er wordt beweerd dat de SCHAKEL niet klopt. Bij een gat-rij is er niets te "
            "vergelijken -- dat is een onware uitspraak, geen ontbrekend bewijs."
        )
        assert resultaat.stored_hash == "", "De opgeslagen hash is leeg; dat hoort zo terug."
