"""`/verify-integrity` kijkt naar de NIEUWSTE rijen, niet de oudste (ADR-036 OP-122).

**De bevinding.** De query was `ORDER BY timestamp ASC ... LIMIT 1000`: de OUDSTE duizend rijen.
Wie zijn sporen in RECENTE regels wist, werd door dit endpoint nooit gezien -- terwijl de
docstring "OWASP A09: Detects log tampering attempts" belooft.

Het endpoint heeft geen `offset` en geen datumparameters, dus een beheerder kan het venster niet
verplaatsen. `limit=10000` maakt het alleen groter vanaf hetzelfde oudste beginpunt. Bij een
tenant met meer dan tienduizend auditregels is manipulatie in de recente rijen per constructie
onzichtbaar.

**Waarom de basislijn gezaaid moet worden.** Neem je het venster vanaf de nieuwste kant, dan
heeft de eerste rij IN het venster een `previous_hash` die naar een rij ERBUITEN wijst. Start de
traversal met een lege basislijn, dan wijkt de hercompute af en heet dat MANIPULATIE -- op een
volkomen gave keten. `verify_chain` heeft dat sinds 2026-08-10 opgelost voor `start_date`; hier
is dezelfde oplossing nodig.

**De bestaande SQL-test bewaakt dit niet.** `test_verify_log_integrity_orders_by_id_as_tiebreak`
doet `assert "audit_logs.id ASC" in sql or "audit_logs.id" in sql.split("ORDER BY")[-1]`. De
tweede tak blijft waar bij `DESC`, dus die test blokkeert de omzetting niet -- maar hij bewaakt
hem ook niet.

**Mutatietest (2026-08-11, beide richtingen):** de sortering terug naar `ASC` -> ROOD. Het zaaien
van de basislijn weggehaald -> ROOD (de eerste rij van het venster meldt dan een valse breuk).
En de andere kant: een gave keten binnen het venster -> GROEN, anders zou "meld altijd
manipulatie" een geldige oplossing zijn.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.hash_chain import HashChainVerifier
from src.core.governance.models import AuditLog
from src.core.security.security_audit_service import SecurityAuditService

_T0 = datetime(2026, 8, 11, 9, 0, 0, tzinfo=timezone.utc)


def _ketting(lengte: int) -> list[AuditLog]:
    """Een correcte keten, oudste eerst."""
    verifier = HashChainVerifier(db_session=None)
    rijen: list[AuditLog] = []
    vorige: str | None = None
    for i in range(lengte):
        rij = AuditLog(
            id=i,
            tenant_id=1,
            action=f"actie_{i}",
            resource=f"bron_{i}",
            timestamp=_T0 + timedelta(minutes=i),
        )
        rij.previous_hash = vorige
        rij.audit_hash = verifier._compute_hash(rij, vorige)
        vorige = rij.audit_hash
        rijen.append(rij)
    return rijen


def _dienst_met(
    venster: list[AuditLog], basislijn: str | None
) -> tuple[SecurityAuditService, AsyncMock]:
    """De sessie geeft eerst het venster terug, daarna de basislijn-lookup."""
    sessie = AsyncMock(spec=AsyncSession)
    venster_resultaat = Mock()
    venster_resultaat.scalars = Mock(return_value=Mock(all=Mock(return_value=venster)))
    basis_resultaat = Mock()
    basis_resultaat.scalar_one_or_none = Mock(return_value=basislijn)
    sessie.execute = AsyncMock(side_effect=[venster_resultaat, basis_resultaat])
    return SecurityAuditService(), sessie


@pytest.mark.asyncio
class TestTheWindowStartsAtTheNewestRows:
    async def test_the_query_takes_the_newest_rows(self):
        """De kern: een aanvaller wist zijn sporen in de RECENTE regels, niet in de oudste."""
        dienst, sessie = _dienst_met([], None)

        await dienst.verify_log_integrity(db=sessie, tenant_id=1, limit=10)

        sql = str(
            sessie.execute.await_args_list[0]
            .args[0]
            .compile(compile_kwargs={"literal_binds": True})
        ).replace("\n", " ")
        order_by = sql.split("ORDER BY")[-1]

        assert "DESC" in order_by, (
            "Het venster begint bij de OUDSTE rijen. Wie recente sporen wist wordt dan nooit "
            f"gezien, terwijl dit endpoint 'Detects log tampering attempts' belooft.\n\n"
            f"ORDER BY was:{order_by}"
        )
        assert "audit_logs.id" in order_by, (
            f"De `id`-tiebreak is verdwenen (ADR-036 OP-110).\n\nORDER BY was:{order_by}"
        )

    async def test_the_baseline_is_seeded_so_the_window_start_is_not_a_false_break(self):
        """De eerste rij van het venster wijst naar een rij ERBUITEN.

        Zonder zaaien meldt die rij een breuk die er niet is -- precies de valse-P0 die bij
        `verify_chain` op 2026-08-10 is opgeruimd.
        """
        keten = _ketting(6)
        venster = keten[3:]  # de database geeft alleen de nieuwste drie terug
        dienst, sessie = _dienst_met(list(reversed(venster)), keten[2].audit_hash)

        uitkomst = await dienst.verify_log_integrity(db=sessie, tenant_id=1, limit=3)

        assert uitkomst["tampering_detected"] is False, (
            f"Een gave keten meldt manipulatie op de eerste rij van het venster. Gevonden: "
            f"{uitkomst['tampered_entries']}"
        )
        assert uitkomst["verified"] is True

    async def test_tampering_inside_the_window_is_still_caught(self):
        """De tweede richting: zonder dit zou 'meld nooit iets' een geldige oplossing zijn."""
        keten = _ketting(6)
        keten[4].action = "STIEKEM_GEWIJZIGD"
        venster = keten[3:]
        dienst, sessie = _dienst_met(list(reversed(venster)), keten[2].audit_hash)

        uitkomst = await dienst.verify_log_integrity(db=sessie, tenant_id=1, limit=3)

        assert uitkomst["tampering_detected"] is True, (
            "Manipulatie BINNEN het venster wordt niet betrapt."
        )
        assert any(e["issue"] == "hash_mismatch" for e in uitkomst["tampered_entries"])
