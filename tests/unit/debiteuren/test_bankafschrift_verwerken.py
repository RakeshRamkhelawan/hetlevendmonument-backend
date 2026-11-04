"""Een heel afschrift verwerken: afvinken, al afgevinkt, niet gekoppeld -- debiteuren vanzelf afronden, B2 (2026-10-20).

`verwerk_afschrift` leest een afschrift, koppelt elke bijschrijving en roept PER af te vinken vordering een
terugroepfunctie aan (`vink_af`); het weet niets van de database. Gemeten met het verzonnen voorbeeldafschrift:

1. Afgevinkt worden precies de vorderingen met een gelijk bedrag en een los factuurnummer (1, 2 en 6, met de datum uit
   het afschrift); de rest staat in "niet gekoppeld" met datum, bedrag, valuta en omschrijving, in volgorde.
2. De tweede bijschrijving voor dezelfde vordering in hetzelfde bestand is `al_afgevinkt` (de terugroep gebeurt een
   keer); een tweede keer hetzelfde afschrift inlezen (de statussen zijn dan betaald) vinkt niets af.
3. Een fout in het bestand komt als `BankafschriftFout` naar buiten ZONDER dat er iets is afgevinkt; een fout in de
   terugroep stopt de verwerking.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.core.services.bankafschrift import BankafschriftFout, Vordering, verwerk_afschrift

VOORBEELD = (
    Path(__file__).resolve().parents[2] / "fixtures" / "bankafschrift" / "camt053_voorbeeld.xml"
)


def _vorderingen() -> list[Vordering]:
    def v(rij_id: int, nummer: str, bedrag: str, status: str = "open") -> Vordering:
        return Vordering(rij_id, nummer, Decimal(bedrag), "EUR", status)

    return [
        v(1, "F-2026-001", "121.00"),
        v(2, "F-2026-002", "250.00", "herinnerd"),
        v(3, "F-2026-003", "100.00"),
        v(4, "F-2026-004", "50.00"),
        v(5, "F-2026-005", "50.00"),
        v(6, "F-2026-006", "60.00", "geescaleerd"),
    ]


class _Opname:
    def __init__(self, fout: Exception | None = None) -> None:
        self.aanroepen: list[tuple[int, date | None]] = []
        self._fout = fout

    async def __call__(self, vordering_id: int, datum: date | None) -> None:
        if self._fout is not None:
            raise self._fout
        self.aanroepen.append((vordering_id, datum))


async def _verwerk(vorderingen: list[Vordering], opname: _Opname):  # noqa: ANN202
    return await verwerk_afschrift(VOORBEELD.read_bytes(), vorderingen, opname)


@pytest.mark.asyncio
class TestHetVoorbeeld:
    async def test_the_right_receivables_are_ticked_off_with_the_date_of_the_statement(
        self,
    ) -> None:
        opname = _Opname()

        verwerking = await _verwerk(_vorderingen(), opname)

        verwacht = [(1, date(2026, 10, 5)), (2, date(2026, 10, 6)), (6, date(2026, 10, 11))]
        assert (opname.aanroepen, verwerking.afgevinkt) == (verwacht, verwacht)

    async def test_the_rest_is_listed_as_not_matched_in_order(self) -> None:
        verwerking = await _verwerk(_vorderingen(), _Opname())

        assert [
            (n.datum, n.bedrag, n.valuta, n.omschrijving) for n in verwerking.niet_gekoppeld
        ] == [
            (date(2026, 10, 7), Decimal("99.99"), "EUR", "Factuur F-2026-003"),
            (date(2026, 10, 8), Decimal("50.00"), "EUR", "Facturen F-2026-004 en F-2026-005"),
            (date(2026, 10, 10), Decimal("75.00"), "EUR", "Cadeau voor het team"),
        ]

    async def test_the_second_payment_for_the_same_receivable_is_already_ticked_off(self) -> None:
        verwerking = await _verwerk(_vorderingen(), _Opname())

        assert verwerking.al_afgevinkt == 1

    async def test_the_counts_are_those_of_the_statement(self) -> None:
        verwerking = await _verwerk(_vorderingen(), _Opname())

        assert (verwerking.aantal_bijschrijvingen, verwerking.overgeslagen) == (7, 1)

    async def test_a_second_run_over_the_same_statement_ticks_nothing_off(self) -> None:
        betaald = [replace(v, status="betaald") if v.id in (1, 2, 6) else v for v in _vorderingen()]
        opname = _Opname()

        verwerking = await _verwerk(betaald, opname)

        assert (opname.aanroepen, verwerking.afgevinkt, verwerking.al_afgevinkt) == ([], [], 4)

    async def test_the_not_matched_list_is_the_same_on_a_second_run(self) -> None:
        eerste = await _verwerk(_vorderingen(), _Opname())
        betaald = [replace(v, status="betaald") if v.id in (1, 2, 6) else v for v in _vorderingen()]

        tweede = await _verwerk(betaald, _Opname())

        assert tweede.niet_gekoppeld == eerste.niet_gekoppeld

    async def test_without_receivables_nothing_is_ticked_off_and_everything_is_listed(self) -> None:
        opname = _Opname()

        verwerking = await _verwerk([], opname)

        assert (opname.aanroepen, len(verwerking.niet_gekoppeld)) == ([], 7)

    async def test_a_receivable_ticked_off_in_this_run_is_not_ticked_off_again(self) -> None:
        # Bijschrijving 1 en 8 horen allebei bij F-2026-001 (121,00): de tweede is al afgevinkt.
        opname = _Opname()

        await _verwerk(_vorderingen(), opname)

        assert [i for i, _ in opname.aanroepen].count(1) == 1


@pytest.mark.asyncio
class TestFouten:
    async def test_a_broken_file_raises_before_anything_is_ticked_off(self) -> None:
        opname = _Opname()

        with pytest.raises(BankafschriftFout):
            await verwerk_afschrift(b"geen xml", _vorderingen(), opname)

        assert opname.aanroepen == []

    async def test_a_failing_callback_stops_the_processing(self) -> None:
        with pytest.raises(RuntimeError):
            await _verwerk(_vorderingen(), _Opname(RuntimeError("database weg")))
