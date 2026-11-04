"""Bankafschrift, nazorg uit Gate 2 ronde 1 (security-review, 2026-10-20).

Drie gaten die de reviewer aanwees en die ik aan de code heb nagelopen:

1. CPU: `MAX_TRANSACTIES` telde alleen `Ntry`-regels. EEN `Ntry` met duizenden `TxDtls` gaf tienduizenden
   bijschrijvingen, elk een lineaire scan over alle vorderingen. Nu: een grens op het aantal BIJSCHRIJVINGEN, en de
   koppelregel krijgt alleen vorderingen met hetzelfde bedrag en dezelfde valuta (een index).
2. Geheugen: een bestand van 5 MB aan lege elementen bouwt een boom van ruim een miljoen knopen voordat de dieptecontrole
   draait. Nu: een grens op het aantal tags VOOR het parsen.
3. Terugboeking: een `TxDtls` met `RtrInf` (retour) of met een eigen debetrichting binnen een geboekte creditregel
   telde als betaling en zette een factuur ten onrechte op betaald. Nu: zo'n transactie is geen bijschrijving.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import time
from decimal import Decimal

import pytest

from src.core.services import bankafschrift
from src.core.services.bankafschrift import (
    MAX_BIJSCHRIJVINGEN,
    BankafschriftFout,
    Vordering,
    lees_camt053,
    verwerk_afschrift,
)


def _tx(omschrijving: str, bedrag: str = "10.00", extra: str = "") -> str:
    return (
        "<TxDtls>"
        f'<AmtDtls><TxAmt><Amt Ccy="EUR">{bedrag}</Amt></TxAmt></AmtDtls>'
        f"{extra}<RmtInf><Ustrd>{omschrijving}</Ustrd></RmtInf>"
        "</TxDtls>"
    )


def _afschrift(entries: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">'
        f"<BkToCstmrStmt><Stmt><Id>S1</Id>{entries}</Stmt></BkToCstmrStmt></Document>"
    ).encode()


def _entry(transacties: str, bedrag: str = "30.00", richting: str = "CRDT") -> str:
    return (
        f'<Ntry><Amt Ccy="EUR">{bedrag}</Amt><CdtDbtInd>{richting}</CdtDbtInd><Sts>BOOK</Sts>'
        f"<BookgDt><Dt>2026-10-05</Dt></BookgDt><NtryDtls>{transacties}</NtryDtls></Ntry>"
    )


class TestAantalBijschrijvingen:
    def test_one_entry_with_too_many_transactions_is_refused(self) -> None:
        zwaar = _entry(_tx("F-1") * (MAX_BIJSCHRIJVINGEN + 1))

        with pytest.raises(BankafschriftFout) as fout:
            lees_camt053(_afschrift(zwaar))

        assert fout.value.code == "TE_VEEL_TRANSACTIES"

    def test_exactly_the_maximum_number_of_transactions_is_read(self) -> None:
        precies = _entry(_tx("F-1") * MAX_BIJSCHRIJVINGEN)

        assert len(lees_camt053(_afschrift(precies)).bijschrijvingen) == MAX_BIJSCHRIJVINGEN

    def test_the_refusal_comes_before_the_work(self) -> None:
        zwaar = _entry(_tx("F-1") * (MAX_BIJSCHRIJVINGEN + 1))
        start = time.perf_counter()

        with pytest.raises(BankafschriftFout):
            lees_camt053(_afschrift(zwaar))

        assert time.perf_counter() - start < 2.0


class TestAantalTags:
    def test_a_valid_looking_file_with_far_too_many_tags_is_refused_before_parsing(self) -> None:
        # Een GELDIG document (met `Stmt`): zonder de tagtelling zou de parser het zonder klacht lezen en leeg teruggeven.
        platte_massa = "<x/>" * (bankafschrift.MAX_TAGS + 1)

        with pytest.raises(BankafschriftFout) as fout:
            lees_camt053(_afschrift(platte_massa))

        assert fout.value.code == "GEEN_GELDIG_AFSCHRIFT"

    def test_the_same_file_below_the_limit_is_read(self) -> None:
        # Tegenproef: zonder deze is "elk groot bestand weigeren" een geldige oplossing.
        minder = "<x/>" * 1000

        assert lees_camt053(_afschrift(minder)).bijschrijvingen == []

    def test_the_limit_leaves_room_for_a_real_statement(self) -> None:
        assert bankafschrift.MAX_TAGS >= 100_000


class TestTerugboeking:
    def test_a_return_inside_a_batch_is_not_a_payment(self) -> None:
        retour = _tx("F-1", "10.00", "<RtrInf><Rsn><Cd>AC04</Cd></Rsn></RtrInf>")
        gewoon = _tx("F-2", "20.00")

        lezing = lees_camt053(_afschrift(_entry(retour + gewoon)))

        assert [b.omschrijving for b in lezing.bijschrijvingen] == ["F-2"]

    def test_the_skipped_return_is_counted_as_skipped(self) -> None:
        retour = _tx("F-1", "10.00", "<RtrInf><Rsn><Cd>AC04</Cd></Rsn></RtrInf>")

        lezing = lees_camt053(_afschrift(_entry(retour + _tx("F-2", "20.00"))))

        assert lezing.overgeslagen == 1

    def test_a_debit_transaction_inside_a_credit_batch_is_not_a_payment(self) -> None:
        debet = _tx("F-1", "10.00", "<CdtDbtInd>DBIT</CdtDbtInd>")

        lezing = lees_camt053(_afschrift(_entry(debet + _tx("F-2", "20.00"))))

        assert [b.omschrijving for b in lezing.bijschrijvingen] == ["F-2"]

    def test_a_credit_transaction_inside_a_credit_batch_is_still_a_payment(self) -> None:
        krediet = _tx("F-1", "10.00", "<CdtDbtInd>CRDT</CdtDbtInd>")

        lezing = lees_camt053(_afschrift(_entry(krediet + _tx("F-2", "20.00"))))

        assert len(lezing.bijschrijvingen) == 2

    def test_a_single_entry_with_a_return_is_not_a_payment(self) -> None:
        retour = (
            "<TxDtls><RtrInf><Rsn><Cd>MS03</Cd></Rsn></RtrInf>"
            "<RmtInf><Ustrd>F-1</Ustrd></RmtInf></TxDtls>"
        )

        lezing = lees_camt053(_afschrift(_entry(retour, "10.00")))

        assert (lezing.bijschrijvingen, lezing.overgeslagen) == ([], 1)


@pytest.mark.asyncio
class TestIndex:
    async def test_the_matching_rule_only_sees_receivables_with_the_same_amount_and_currency(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gezien: list[int] = []
        echte_koppel = bankafschrift.koppel

        def _spion(bijschrijving, vorderingen):  # noqa: ANN001, ANN202
            gezien.append(len(vorderingen))
            return echte_koppel(bijschrijving, vorderingen)

        monkeypatch.setattr(bankafschrift, "koppel", _spion)
        vorderingen = [Vordering(i, f"F-{i}", Decimal(i), "EUR", "open") for i in range(1, 101)]
        data = _afschrift(_entry(_tx("F-7", "7.00"), "7.00"))

        async def _niets(_id: int, _datum: object) -> None:
            return None

        await verwerk_afschrift(data, vorderingen, _niets)

        assert gezien == [1]

    async def test_the_index_still_ticks_off_the_right_receivable(self) -> None:
        vorderingen = [Vordering(i, f"F-{i}", Decimal(i), "EUR", "open") for i in range(1, 101)]
        afgevinkt: list[int] = []

        async def _noteer(rij_id: int, _datum: object) -> None:
            afgevinkt.append(rij_id)

        await verwerk_afschrift(
            _afschrift(_entry(_tx("F-7", "7.00"), "7.00")), vorderingen, _noteer
        )

        assert afgevinkt == [7]

    async def test_a_receivable_ticked_off_in_this_run_is_not_ticked_off_again(self) -> None:
        vorderingen = [Vordering(1, "F-1", Decimal("5.00"), "EUR", "open")]
        afgevinkt: list[int] = []

        async def _noteer(rij_id: int, _datum: object) -> None:
            afgevinkt.append(rij_id)

        dubbel = _entry(_tx("F-1", "5.00") + _tx("F-1", "5.00"), "10.00")
        await verwerk_afschrift(_afschrift(dubbel), vorderingen, _noteer)

        assert afgevinkt == [1]
