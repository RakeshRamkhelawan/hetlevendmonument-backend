"""Een gat van VOOR de fixdatum is bekend; een gat van NA die datum is verdacht (ADR-036 OP-108).

**De bevinding.** OP-108 is op 2026-08-10 GEDEELTELIJK opgelost: beide levende rauwe schrijvers
gaan sindsdien via `AuditService.log_event`, dus nieuwe rijen krijgen wel een `audit_hash`. Voor de
rijen die de opruimactor daarvoor heeft geschreven bestaat GEEN backfill -- omhashen zou de
bewijswaarde van de keten vernietigen. Gevolg voor `/integrity/verify`: elke tenant die de
opruimactor ooit heeft geraakt houdt `unhashed_entries > 0` en dus permanent `is_valid=False`.

Een oordeel dat altijd False is, is geen oordeel. Zolang gaten de normale toestand zijn verdwijnt
een aanvaller die een hash LEEGMAAKT in de ruis -- precies wat OP-118 als restrisico benoemt.

**Het watermerk.** `UNHASHED_GAP_WATERMARK` is een HARDE datum. Gaten op rijen van VOOR die datum
zijn de bekende, geregistreerde OP-108-gaten en tellen niet meer mee in `is_valid`. Gaten op rijen
van NA die datum horen niet te bestaan -- alle schrijvers vullen de keten -- en blijven `is_valid`
op False zetten.

**Waarom dit geen achterdeur is.** Het watermerk verzacht het oordeel UITSLUITEND voor rijen met
een tijdstempel voor de datum. De datum is een module-constante, geen parameter en geen
omgevingsvariabele: een aanroeper kan hem niet opschuiven. De tests
`test_a_gap_after_the_watermark_still_fails_loudly` en
`test_tampering_after_the_watermark_is_still_caught_despite_legacy_gaps` zijn de tegenhelft --
zonder die twee zou "noem alles oud" een geldige oplossing zijn.

**Mutatietest (beide richtingen), een regel per element van de verzameling {voor, na, geen}:**
- `unhashed_after_watermark` uit `is_valid` halen (`is_valid = not tampering_detected`)
  -> ROOD op `test_a_gap_after_the_watermark_still_fails_loudly`.
- Het watermerk naar `datetime.max` zetten (alles is "oud")
  -> ROOD op `test_a_gap_after_the_watermark_still_fails_loudly`.
- Het watermerk naar `datetime.min` zetten (niets is "oud")
  -> ROOD op `test_a_gap_before_the_watermark_no_longer_invalidates_the_chain`.
- Rijen zonder tijdstempel als "voor" classificeren i.p.v. "na"
  -> ROOD op `test_a_gap_without_a_timestamp_counts_as_recent`.
- Een keten ZONDER gaten -> blijft GROEN op `test_an_intact_chain_is_still_valid` (de legitieme
  kant: het watermerk mag geen enkel bestaand oordeel omdraaien).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.hash_chain import UNHASHED_GAP_WATERMARK, HashChainVerifier
from src.core.governance.models import AuditLog

#: ABSOLUTE datums, NIET afgeleid van `UNHASHED_GAP_WATERMARK`.
#:
#: Eerst stond hier `UNHASHED_GAP_WATERMARK -/+ timedelta(days=30)`. Dat was een test die zijn
#: eigen invoer aan BEIDE kanten van de vergelijking verzint: verschuif de constante en de
#: testdata schuift mee, dus elke waarde is dan groen. Gemeten: het watermerk op 1970 zetten
#: liet alle 18 tests staan. Met absolute datums valt die mutatie wel om.
#: Ruim voor de fixdatum -- de bekende OP-108-gaten van de opruimactor.
_OUD = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
#: Ruim erna -- sinds de fix hoort hier geen ongehashte rij meer bij te komen.
_NIEUW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def _verifier(entries: list[AuditLog]) -> HashChainVerifier:
    """Een verifier die exact deze rijen teruggeeft."""
    sessie = AsyncMock(spec=AsyncSession)
    resultaat = Mock()
    resultaat.scalars = Mock(return_value=Mock(all=Mock(return_value=entries)))
    sessie.execute = AsyncMock(return_value=resultaat)
    return HashChainVerifier(db_session=sessie)


def _ketting(basis: datetime, lengte: int, *, gat_op: int | None = None) -> list[AuditLog]:
    """Een correcte keten vanaf `basis`, eventueel met een ONGEHASHTE rij op `gat_op`.

    Het gat wordt gebouwd zoals de rauwe schrijvers het deden: `audit_hash` EN `previous_hash`
    allebei NULL, en de keten loopt er DOORHEEN.
    """
    verifier = HashChainVerifier(db_session=None)  # type: ignore[arg-type]
    rijen: list[AuditLog] = []
    vorige: str | None = None
    for i in range(lengte):
        rij = AuditLog(
            id=i,
            tenant_id=1,
            action=f"actie_{i}",
            resource=f"bron_{i}",
            timestamp=basis + timedelta(minutes=i),
        )
        if i == gat_op:
            rij.audit_hash = None
            rij.previous_hash = None
            rijen.append(rij)
            continue
        rij.previous_hash = vorige
        rij.audit_hash = verifier._compute_hash(rij, vorige)
        vorige = rij.audit_hash
        rijen.append(rij)
    return rijen


@pytest.mark.asyncio
class TestTheUnhashedGapWatermark:
    async def test_the_watermark_is_a_hard_constant_not_a_knob(self) -> None:
        """De datum mag niet instelbaar zijn -- anders is hij per aanroep te verschuiven."""
        import inspect

        parameters = set(inspect.signature(HashChainVerifier.verify_chain).parameters)
        assert "watermark" not in parameters and "unhashed_gap_watermark" not in parameters, (
            "Het watermerk is een parameter van verify_chain geworden. Dan kan een aanroeper "
            "elk gat als 'oud' laten gelden en is het een generieke ontsnapping."
        )
        assert UNHASHED_GAP_WATERMARK.tzinfo is not None, "Het watermerk moet timezone-aware zijn."
        # De WAARDE vastpinnen, niet alleen het bestaan. Zonder deze assertie kan de datum stil
        # opschuiven en blijft alles groen -- de rest van dit bestand gebruikt absolute datums,
        # maar die dekken alleen de twee kanten, niet de exacte grens.
        assert UNHASHED_GAP_WATERMARK == datetime(2026, 8, 10, tzinfo=timezone.utc), (
            "De fixdatum van OP-108 is verschoven. Dat verandert welke gaten als 'bekend' "
            "gelden en is een bewuste beslissing, geen bijvangst."
        )

    async def test_an_intact_chain_is_still_valid(self) -> None:
        """De legitieme kant: zonder gaten verandert het watermerk niets."""
        resultaat = await _verifier(_ketting(_NIEUW, 4)).verify_chain(tenant_id=1)

        assert resultaat.is_valid is True
        assert resultaat.unhashed_entries == 0
        assert resultaat.unhashed_before_watermark == 0
        assert resultaat.unhashed_after_watermark == 0

    async def test_a_gap_before_the_watermark_no_longer_invalidates_the_chain(self) -> None:
        """DE BEVINDING. Een bekend OP-108-gat maakte het oordeel permanent onbruikbaar."""
        resultaat = await _verifier(_ketting(_OUD, 4, gat_op=1)).verify_chain(tenant_id=1)

        assert resultaat.unhashed_entries == 1, "Het gat wordt niet meer geteld."
        assert resultaat.unhashed_before_watermark == 1, (
            "Een gat van voor de fixdatum wordt niet als bekend gat herkend."
        )
        assert resultaat.unhashed_after_watermark == 0
        assert resultaat.tampering_detected is False
        assert resultaat.is_valid is True, (
            "Een keten waarvan het ENIGE gebrek een bekend OP-108-gat van voor de fixdatum is, "
            "geldt nog steeds als ongeldig. Dan is is_valid permanent False voor elke tenant die "
            "de opruimactor ooit heeft geraakt, en verdwijnt echte manipulatie in de ruis."
        )

    async def test_a_gap_after_the_watermark_still_fails_loudly(self) -> None:
        """DE TEGENHELFT. Zonder deze test is het watermerk een achterdeur.

        Sinds de fix vult elke schrijver de keten. Een ongehashte rij NA de fixdatum is dus per
        definitie verdacht -- dat is exact het hash-strippen dat OP-118 beschrijft.
        """
        resultaat = await _verifier(_ketting(_NIEUW, 4, gat_op=1)).verify_chain(tenant_id=1)

        assert resultaat.unhashed_after_watermark == 1, (
            "Een gat NA de fixdatum wordt niet apart geteld."
        )
        assert resultaat.unhashed_before_watermark == 0
        assert resultaat.is_valid is False, (
            "Een gat NA de fixdatum laat de keten als GELDIG gelden. Het watermerk is dan een "
            "generieke ontsnapping: wie een hash leegmaakt wordt weggeschreven als legacy."
        )

    async def test_a_gap_without_a_timestamp_counts_as_recent(self) -> None:
        """Fail-secure: een rij zonder tijdstempel is niet aantoonbaar oud, dus telt hij als nieuw.

        Zou dit andersom zijn, dan is de tijdstempel leegmaken de manier om onder het watermerk
        te duiken -- en die kolom is voor een ONGEHASHTE rij door niets beschermd.
        """
        rijen = _ketting(_NIEUW, 4, gat_op=1)
        rijen[1].timestamp = None  # type: ignore[assignment]

        resultaat = await _verifier(rijen).verify_chain(tenant_id=1)

        assert resultaat.unhashed_after_watermark == 1, (
            "Een gat zonder tijdstempel wordt als 'oud' weggeschreven. Dat maakt het leegmaken "
            "van de tijdstempel tot de ontsnappingsroute."
        )
        assert resultaat.is_valid is False

    async def test_tampering_after_the_watermark_is_still_caught_despite_legacy_gaps(self) -> None:
        """Het watermerk mag de MANIPULATIE-detectie niet aanraken, alleen het gat-oordeel."""
        rijen = _ketting(_OUD, 5, gat_op=1)
        rijen[3].action = "STIEKEM_GEWIJZIGD"  # hash blijft de oude -> hercompute valt om

        resultaat = await _verifier(rijen).verify_chain(tenant_id=1)

        assert resultaat.tampering_detected is True, (
            "Manipulatie wordt niet meer betrapt zodra er een legacy-gat in de keten zit."
        )
        assert resultaat.is_valid is False
        assert resultaat.broken_at_entry_id == rijen[3].id
