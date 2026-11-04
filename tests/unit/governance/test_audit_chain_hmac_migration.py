"""De omschakeling naar een gesleutelde ketenhash, zonder bestaande ketens te breken (OP-120).

**Waarom een markering per rij en niet gewoon omzetten.** Zonder markering rekent de verifier
elke bestaande rij na met het NIEUWE algoritme, en dan komt er geen enkele hash meer uit. Gemeten
gevolg van een naieve omschakeling: `tampering_detected=True` -- het veld dat in `schemas.py` is
gedocumenteerd als "the P0 signal" -- voor ELKE tenant, op vier endpoints tegelijk, permanent.
Dat is exact de valse-P0-klasse die bij OP-108 net is opgeruimd.

**Wat de markering WEL en NIET doet -- gecorrigeerd 2026-08-11 na de mutatietest.** Hier stond dat
de markering in de preimage MOET omdat hij anders te omzeilen is. Dat bleek onjuist: het weghalen
van `ALGORITHM_NAME` uit de preimage liet alle tests groen. Wat het terugzetten van de markering
betrapt is de DISPATCH, niet de preimage -- de rij valt dan in de legacy-tak en de sleutelloze
`sha256(...)` levert iets anders op dan de opgeslagen `chain_mac(...)`. De markering blijft in de
preimage als extra binding, maar hij draagt deze bescherming niet.

**Het knippunt is wat de echte aanval stopt.** Een aanvaller die de markering wist EN de
sleutelloze hash opnieuw uitrekent, levert een keten op waarin alles klopt. Alleen een knippunt
per tenant (`audit_chain_anchors.chain_epoch_id`) maakt een ongesleutelde rij NA dat punt zelf een
afwijking. Dat knippunt leeft in de ankertabel uit OP-119 -- daarom moest die eerst.

**De grens, eerlijk:** het knippunt staat in dezelfde database. Wie de ankerrij kan verwijderen,
zet de nulmeting terug. Dat is opgeschreven in ADR-019 en niet weggepoetst.

**Mutatietest (2026-08-11, beide richtingen, gemeten):**
- dispatch omgezet zodat legacy-rijen ook met HMAC worden nagerekend -> ROOD;
- knippunt genegeerd -> ROOD;
- markering uit de preimage gehaald -> **GROEN**, en dat is de reden dat de tekst hierboven is
  gecorrigeerd. Een mutatie die groen blijft is een claim die niet klopt;
- gemengde keten zonder manipulatie -> GROEN, anders zou "meld altijd manipulatie" een geldige
  oplossing zijn.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.audit_chain_key import ALGORITHM_NAME
from src.core.governance.hash_chain import HashChainVerifier
from src.core.governance.models import AuditLog

_T0 = datetime(2026, 8, 11, 12, 0, 0, tzinfo=timezone.utc)


def _verifier(entries: list[AuditLog]) -> HashChainVerifier:
    sessie = AsyncMock(spec=AsyncSession)
    resultaat = Mock()
    resultaat.scalars = Mock(return_value=Mock(all=Mock(return_value=entries)))
    sessie.execute = AsyncMock(return_value=resultaat)
    return HashChainVerifier(db_session=sessie)


def _gemengde_ketting(legacy: int, gesleuteld: int) -> list[AuditLog]:
    """Een keten die begint in SHA-256 en overgaat op HMAC -- de echte migratievorm."""
    verifier = HashChainVerifier(db_session=None)
    rijen: list[AuditLog] = []
    vorige: str | None = None
    for i in range(legacy + gesleuteld):
        rij = AuditLog(
            id=i,
            tenant_id=1,
            action=f"actie_{i}",
            resource=f"bron_{i}",
            timestamp=_T0 + timedelta(minutes=i),
        )
        rij.hash_algorithm = None if i < legacy else ALGORITHM_NAME
        rij.previous_hash = vorige
        rij.audit_hash = verifier._compute_hash(rij, vorige)
        vorige = rij.audit_hash
        rijen.append(rij)
    return rijen


@pytest.mark.asyncio
class TestTheKeyedChainDoesNotBreakHistory:
    async def test_a_mixed_chain_verifies_clean(self):
        """De kern: bestaande rijen mogen NIET als manipulatie gemeld worden."""
        resultaat = await _verifier(_gemengde_ketting(legacy=5, gesleuteld=3)).verify_chain(
            tenant_id=1
        )

        assert resultaat.tampering_detected is False, (
            "Een gemengde keten meldt manipulatie. Zonder markering per rij rekent de verifier "
            "legacy-rijen na met het nieuwe algoritme, en dan meldt ELKE bestaande tenant een P0 "
            "op vier endpoints tegelijk."
        )
        assert resultaat.verified_entries == 8
        assert resultaat.is_valid is True

    async def test_flipping_the_marker_alone_breaks_the_hash(self):
        """De markering terugzetten ZONDER de hash mee te herberekenen wordt betrapt.

        **Wat deze test WEL en NIET bewijst -- gecorrigeerd 2026-08-11 na een mutatietest.**
        Hij stond hier eerst als bewijs dat de markering in de PREIMAGE zit. Dat was onjuist: bij
        het weghalen van `ALGORITHM_NAME` uit de preimage bleef deze test groen. Wat hem rood
        maakt is de DISPATCH -- de rij valt in de legacy-tak en `sha256(...)` levert iets anders
        op dan de opgeslagen `chain_mac(...)`.

        De markering blijft in de preimage als extra binding, maar hij is niet wat deze aanval
        stopt, en de test beweert dat nu ook niet meer.

        **De ECHTE aanval** -- markering wissen EN de sleutelloze hash opnieuw uitrekenen -- is
        hiermee niet afgedekt. Alleen het knippunt stopt die; zie de test hieronder. Dat is
        precies waarom het knippunt bestaat en waarom de ankertabel er eerst moest zijn.
        """
        rijen = _gemengde_ketting(legacy=0, gesleuteld=3)
        rijen[1].hash_algorithm = None  # markering weg, hash ONgewijzigd

        resultaat = await _verifier(rijen).verify_chain(tenant_id=1)

        assert resultaat.tampering_detected is True, (
            "De markering is gewist zonder de hash aan te passen, en dat wordt niet betrapt. De "
            "dispatch hoort dan in de legacy-tak te vallen en een andere waarde te berekenen."
        )

    async def test_a_keyless_row_after_the_cutoff_is_an_anomaly(self):
        """Het knippunt: na de omschakeling hoort er geen legacy-rij meer bij te komen."""
        rijen = _gemengde_ketting(legacy=2, gesleuteld=3)
        # Het knippunt ligt bij de eerste gesleutelde rij (id=2).
        resultaat = await _verifier(rijen).verify_chain(tenant_id=1, chain_epoch_id=2)

        assert resultaat.tampering_detected is False, (
            "Een correcte gemengde keten met knippunt meldt manipulatie."
        )

        # Nu een aanvaller die NA het knippunt een sleutelloze rij invoegt met kloppende SHA-256.
        vervalst = _gemengde_ketting(legacy=2, gesleuteld=3)
        doel = vervalst[3]
        doel.hash_algorithm = None
        verifier = HashChainVerifier(db_session=None)
        doel.audit_hash = verifier._compute_hash(doel, vervalst[2].audit_hash)
        vervalst[4].previous_hash = doel.audit_hash
        vervalst[4].audit_hash = verifier._compute_hash(vervalst[4], doel.audit_hash)

        resultaat2 = await _verifier(vervalst).verify_chain(tenant_id=1, chain_epoch_id=2)

        assert resultaat2.tampering_detected is True, (
            "Een sleutelloze rij NA het knippunt wordt niet betrapt. De hashes kloppen allemaal "
            "-- dat is juist het punt: zonder knippunt is teruggaan naar het oude algoritme een "
            "geldige manier om de sleutel te omzeilen."
        )

    async def test_without_a_cutoff_the_verifier_stays_lenient(self):
        """De tweede richting, en een bewuste keuze.

        De drie admin-endpoints geven geen knippunt mee -- die kennen de ankertabel niet. Dan
        gedraagt de verificatie zich als vandaag: legacy-rijen zijn toegestaan. De strengere
        controle draait in de JOB, die het knippunt uit het anker haalt. Zonder deze test zou
        "eis overal HMAC" een geldige oplossing zijn, en dan meldt elk endpoint elke bestaande
        tenant als gemanipuleerd.
        """
        rijen = _gemengde_ketting(legacy=2, gesleuteld=3)
        rijen[3].hash_algorithm = None
        verifier = HashChainVerifier(db_session=None)
        rijen[3].audit_hash = verifier._compute_hash(rijen[3], rijen[2].audit_hash)
        rijen[4].previous_hash = rijen[3].audit_hash
        rijen[4].audit_hash = verifier._compute_hash(rijen[4], rijen[3].audit_hash)

        resultaat = await _verifier(rijen).verify_chain(tenant_id=1)

        assert resultaat.tampering_detected is False, (
            "Zonder knippunt hoort de verificatie zich te gedragen als voorheen."
        )


def test_the_algorithm_name_is_pinned() -> None:
    """De naam staat in de database en mag niet stilletjes veranderen.

    Wijzigt hij, dan valt elke bestaande gesleutelde rij terug in de legacy-tak en verifieert
    hij niet meer -- zonder dat er iets is gemanipuleerd.
    """
    assert ALGORITHM_NAME == "hmac-sha256-v1"
