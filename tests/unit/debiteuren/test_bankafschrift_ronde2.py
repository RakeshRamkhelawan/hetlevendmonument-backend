"""Bankafschrift, Gate 2 ronde 2 (security-review, 2026-10-20): werkplafond, slotvolgorde en gelijktijdigheid.

Wat de reviewer in ronde 2 aanwees en ik aan de code heb nagelopen:

N2. De index sluit alleen op bedrag en valuta. Honderden facturen met hetzelfde bedrag (abonnementen) en duizenden
    bijschrijvingen met dat bedrag geven nog steeds bijschrijvingen x kandidaten vergelijkingen op de event loop. Nu:
    een plafond op het TOTALE werk, geweigerd VOORDAT er iets is afgevinkt, en het lezen van het bestand draait buiten
    de event loop.
N4. De vorderingen werden in bestandsvolgorde gelockt: twee uploads met dezelfde facturen in een andere volgorde kunnen
    elkaar in een deadlock zetten. Nu: afvinken gebeurt in oplopende id-volgorde, en een deadlock of lock-timeout geeft
    een nette 409 in het Nederlands in plaats van een 500.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import threading
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError

from src.core.api.v1.receivables import dependencies
from src.core.services import bankafschrift
from src.core.services.bankafschrift import (
    MAX_VERGELIJKINGEN,
    BankafschriftFout,
    Vordering,
    verwerk_afschrift,
)


def _tx(omschrijving: str, bedrag: str) -> str:
    return (
        "<TxDtls>"
        f'<AmtDtls><TxAmt><Amt Ccy="EUR">{bedrag}</Amt></TxAmt></AmtDtls>'
        f"<RmtInf><Ustrd>{omschrijving}</Ustrd></RmtInf></TxDtls>"
    )


def _afschrift(transacties: str, totaal: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"><BkToCstmrStmt><Stmt><Id>S</Id>'
        f'<Ntry><Amt Ccy="EUR">{totaal}</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts>BOOK</Sts>'
        f"<BookgDt><Dt>2026-10-05</Dt></BookgDt><NtryDtls>{transacties}</NtryDtls></Ntry>"
        "</Stmt></BkToCstmrStmt></Document>"
    ).encode()


async def _noteer_niet(_rij_id: int, _datum: object) -> None:
    return None


def _facturen(aantal: int, bedrag: str = "5.00") -> list[Vordering]:
    return [Vordering(i, f"F-{i}", Decimal(bedrag), "EUR", "open") for i in range(1, aantal + 1)]


@pytest.mark.asyncio
class TestWerkplafond:
    async def test_too_much_work_is_refused(self) -> None:
        # 2000 facturen en 3000 bijschrijvingen met hetzelfde bedrag: 6 miljoen vergelijkingen.
        data = _afschrift(_tx("geen nummer", "5.00") * 3000, "15000.00")
        assert 2000 * 3000 > MAX_VERGELIJKINGEN

        with pytest.raises(BankafschriftFout) as fout:
            await verwerk_afschrift(data, _facturen(2000), _noteer_niet)

        assert fout.value.code == "TE_VEEL_WERK"

    async def test_nothing_is_ticked_off_when_the_work_is_refused(self) -> None:
        data = _afschrift(_tx("F-1", "5.00") * 3000, "15000.00")
        genoteerd: list[int] = []

        async def _noteer(rij_id: int, _datum: object) -> None:
            genoteerd.append(rij_id)

        with pytest.raises(BankafschriftFout):
            await verwerk_afschrift(data, _facturen(2000), _noteer)

        assert genoteerd == []

    async def test_a_normal_statement_stays_far_below_the_limit(self) -> None:
        data = _afschrift(_tx("F-7", "5.00") * 20, "100.00")

        verwerking = await verwerk_afschrift(data, _facturen(200), _noteer_niet)

        assert verwerking.aantal_bijschrijvingen == 20

    async def test_the_limit_counts_candidates_not_receivables(self) -> None:
        # Veel facturen, maar met een ander bedrag dan de bijschrijvingen: geen kandidaten, dus geen werk.
        data = _afschrift(_tx("geen nummer", "5.00") * 3000, "15000.00")

        verwerking = await verwerk_afschrift(data, _facturen(5000, "9.00"), _noteer_niet)

        assert len(verwerking.niet_gekoppeld) == 3000

    async def test_the_file_is_read_off_the_event_loop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        draden: list[str] = []
        echte = bankafschrift.lees_camt053

        def _spion(data: bytes) -> Any:
            draden.append(threading.current_thread().name)
            return echte(data)

        monkeypatch.setattr(bankafschrift, "lees_camt053", _spion)

        await verwerk_afschrift(_afschrift(_tx("F-1", "5.00"), "5.00"), [], _noteer_niet)

        assert draden and draden[0] != threading.main_thread().name


@pytest.mark.asyncio
class TestSlotvolgorde:
    @staticmethod
    def _vorderingen() -> list[Vordering]:
        return [
            Vordering(1, "F-1", Decimal("10.00"), "EUR", "open"),
            Vordering(6, "F-6", Decimal("20.00"), "EUR", "open"),
        ]

    async def test_ticking_off_happens_in_ascending_id_order(self) -> None:
        # Het bestand noemt F-6 eerst en F-1 daarna; twee uploads in verschillende volgorde mogen elkaar niet vastzetten.
        data = _afschrift(_tx("F-6", "20.00") + _tx("F-1", "10.00"), "30.00")
        volgorde: list[int] = []

        async def _noteer(rij_id: int, _datum: object) -> None:
            volgorde.append(rij_id)

        await verwerk_afschrift(data, self._vorderingen(), _noteer)

        assert volgorde == [1, 6]

    async def test_the_result_still_lists_the_receivables_in_statement_order(self) -> None:
        data = _afschrift(_tx("F-6", "20.00") + _tx("F-1", "10.00"), "30.00")

        verwerking = await verwerk_afschrift(data, self._vorderingen(), _noteer_niet)

        assert [rij_id for rij_id, _ in verwerking.afgevinkt] == [6, 1]


def _repo() -> SimpleNamespace:
    async def _lijst(_tenant: int, *, limit: int) -> list[Any]:
        return []

    async def _niets() -> None:
        return None

    return SimpleNamespace(
        list_all_for_matching=_lijst, db=SimpleNamespace(rollback=_niets, commit=_niets)
    )


def _faal_met(sqlstate: str) -> Any:
    async def _faal(*_args: Any, **_kwargs: Any) -> Any:
        raise DBAPIError("statement", {}, SimpleNamespace(pgcode=sqlstate))  # type: ignore[arg-type]

    return _faal


@pytest.mark.asyncio
class TestDeadlock:
    @pytest.mark.parametrize("sqlstate", ["40P01", "55P03"])
    async def test_a_deadlock_or_lock_timeout_gives_a_dutch_409(
        self, monkeypatch: pytest.MonkeyPatch, sqlstate: str
    ) -> None:
        monkeypatch.setattr(bankafschrift, "verwerk_afschrift", _faal_met(sqlstate))

        with pytest.raises(HTTPException) as fout:
            await dependencies.verwerk_bankafschrift(_repo(), tenant_id=1, user_id=1, data=b"x")  # type: ignore[arg-type]

        assert (fout.value.status_code, "opnieuw" in str(fout.value.detail)) == (409, True)

    async def test_another_database_error_is_not_hidden_as_a_409(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bankafschrift, "verwerk_afschrift", _faal_met("23505"))

        with pytest.raises(DBAPIError):
            await dependencies.verwerk_bankafschrift(_repo(), tenant_id=1, user_id=1, data=b"x")  # type: ignore[arg-type]


class _TelStr(str):
    """Een tekst die telt hoe vaak hij naar kleine letters wordt omgezet."""

    aantal = 0

    def lower(self) -> str:
        type(self).aantal += 1
        return super().lower()


@pytest.mark.asyncio
class TestKoppellus:
    """Gerichte review F2: de koppellus draaide op de event loop en zette per kandidaat de omschrijving om."""

    async def test_the_matching_loop_runs_off_the_event_loop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        draden: list[str] = []
        echte = bankafschrift.koppel

        def _spion(bijschrijving: Any, vorderingen: Any) -> Any:
            draden.append(threading.current_thread().name)
            return echte(bijschrijving, vorderingen)

        monkeypatch.setattr(bankafschrift, "koppel", _spion)

        await verwerk_afschrift(_afschrift(_tx("F-1", "5.00"), "5.00"), _facturen(3), _noteer_niet)

        assert draden and all(naam != threading.main_thread().name for naam in draden)

    async def test_the_ceiling_is_five_hundred_thousand(self) -> None:
        assert MAX_VERGELIJKINGEN <= 500_000

    async def test_a_statement_just_over_the_ceiling_is_refused(self) -> None:
        # 600 facturen en 1000 bijschrijvingen met hetzelfde bedrag: 600.000 vergelijkingen.
        data = _afschrift(_tx("geen nummer", "5.00") * 1000, "5000.00")

        with pytest.raises(BankafschriftFout) as fout:
            await verwerk_afschrift(data, _facturen(600), _noteer_niet)

        assert fout.value.code == "TE_VEEL_WERK"

    async def test_the_description_is_lowercased_once_per_payment_not_per_candidate(self) -> None:
        from datetime import date

        from src.core.services.bankafschrift import Bijschrijving, koppel

        _TelStr.aantal = 0
        bijschrijving = Bijschrijving(
            date(2026, 10, 5), Decimal("5.00"), "EUR", _TelStr("betaling zonder nummer")
        )

        koppel(bijschrijving, _facturen(300))

        assert _TelStr.aantal == 1

    async def test_the_result_is_the_same_as_before_for_a_normal_statement(self) -> None:
        data = _afschrift(_tx("betaling F-7", "5.00"), "5.00")
        afgevinkt: list[int] = []

        async def _noteer(rij_id: int, _datum: object) -> None:
            afgevinkt.append(rij_id)

        await verwerk_afschrift(data, _facturen(10), _noteer)

        assert afgevinkt == [7]
