"""De telregels van de bonlezermeting (bonlezer dag 1).

Een meting die zelf onjuist telt, geeft een goed ogend getal over een slecht resultaat. Daarom
worden de regels van `src/core/als/bonlezer/meting.py` hier los getest, met kleine antwoorden.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from src.core.als.bonlezer.meting import (
    DocumentUitslag,
    beoordeel,
    onverwachte_tarieven,
    tel,
)
from src.core.als.bonlezer.veldenlaag import BonVelden

ANTWOORDEN = {
    "leverancier": "Bakkerij De Gouden Korst",
    "datum": "2026-10-15",
    "totaal": "7.23",
    "factuurnummer": None,
    "btw": {"9": "0.58"},
    "btw_nummer": "NL123456789B01",
    "kvk_nummer": "12345678",
}

GOED = BonVelden(
    leverancier="BAKKERIJ DE GOUDEN KORST",
    datum=date(2026, 10, 15),
    totaal=Decimal("7.23"),
    factuurnummer=None,
    btw={9: Decimal("0.58")},
    btw_nummer="NL123456789B01",
    kvk_nummer="12345678",
)


class TestBeoordeel:
    def test_a_fully_correct_reading_is_good_everywhere_it_applies(self) -> None:
        resultaat = beoordeel(GOED, ANTWOORDEN)

        assert all(waarde is not False for waarde in resultaat.values())

    def test_a_total_one_cent_off_is_wrong(self) -> None:
        assert beoordeel(replace(GOED, totaal=Decimal("7.24")), ANTWOORDEN)["totaal"] is False

    def test_a_missing_total_is_wrong_not_skipped(self) -> None:
        assert beoordeel(replace(GOED, totaal=None), ANTWOORDEN)["totaal"] is False

    def test_the_supplier_ignores_case_and_punctuation(self) -> None:
        velden = replace(GOED, leverancier="bakkerij, de gouden  korst!")

        assert beoordeel(velden, ANTWOORDEN)["leverancier"] is True

    def test_another_supplier_is_wrong(self) -> None:
        velden = replace(GOED, leverancier="Bakkerij Anders")

        assert beoordeel(velden, ANTWOORDEN)["leverancier"] is False

    def test_a_wrong_date_is_wrong(self) -> None:
        assert beoordeel(replace(GOED, datum=date(2026, 10, 14)), ANTWOORDEN)["datum"] is False

    def test_a_missing_date_is_wrong(self) -> None:
        assert beoordeel(replace(GOED, datum=None), ANTWOORDEN)["datum"] is False

    def test_a_rate_that_is_not_in_the_answer_is_not_applicable(self) -> None:
        assert beoordeel(GOED, ANTWOORDEN)["btw_21"] is None

    def test_a_missing_vat_amount_is_wrong_when_the_answer_has_that_rate(self) -> None:
        assert beoordeel(replace(GOED, btw={}), ANTWOORDEN)["btw_9"] is False

    def test_a_wrong_vat_amount_is_wrong(self) -> None:
        velden = replace(GOED, btw={9: Decimal("0.57")})

        assert beoordeel(velden, ANTWOORDEN)["btw_9"] is False

    def test_a_receipt_that_gets_an_invoice_number_is_wrong(self) -> None:
        velden = replace(GOED, factuurnummer="123")

        assert beoordeel(velden, ANTWOORDEN)["factuurnummer"] is False


class TestOnverwachteTarieven:
    def test_a_rate_found_but_not_in_the_answer_is_reported(self) -> None:
        velden = replace(GOED, btw={9: Decimal("0.58"), 21: Decimal("1.00")})

        assert onverwachte_tarieven(velden, ANTWOORDEN) == [21]

    def test_no_surprise_when_the_rates_match(self) -> None:
        assert onverwachte_tarieven(GOED, ANTWOORDEN) == []


class TestTel:
    def test_it_counts_good_over_applicable_and_skips_not_applicable(self) -> None:
        uitslagen = [
            DocumentUitslag("a", "bon_foto", {"totaal": True, "btw_21": None}, []),
            DocumentUitslag("b", "bon_foto", {"totaal": False, "btw_21": True}, []),
            DocumentUitslag("c", "bon_foto", {"totaal": True, "btw_21": False}, []),
        ]

        geteld = tel(uitslagen)

        assert (geteld["totaal"], geteld["btw_21"]) == ((2, 3), (1, 2))

    def test_a_field_without_any_applicable_document_counts_zero_of_zero(self) -> None:
        assert tel([])["totaal"] == (0, 0)


class TestFactuurnummerVoorEenKassabon:
    def test_a_receipt_without_an_invoice_number_that_reads_none_is_not_applicable(self) -> None:
        """12 kassabonnen telden als 12 goede factuurnummers; de score hoort over facturen te gaan."""
        assert beoordeel(GOED, ANTWOORDEN)["factuurnummer"] is None

    def test_an_invoice_with_the_right_number_is_good(self) -> None:
        antwoorden = {**ANTWOORDEN, "factuurnummer": "2026-665"}
        velden = replace(GOED, factuurnummer="2026-665")

        assert beoordeel(velden, antwoorden)["factuurnummer"] is True

    def test_an_invoice_whose_number_is_not_read_is_wrong(self) -> None:
        antwoorden = {**ANTWOORDEN, "factuurnummer": "2026-665"}

        assert beoordeel(GOED, antwoorden)["factuurnummer"] is False
