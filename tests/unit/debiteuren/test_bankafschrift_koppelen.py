"""Een bijschrijving koppelen aan een vordering -- debiteuren vanzelf afronden, B2 (2026-10-20).

De koppelregel (`koppel`) is bewust streng, want een verkeerde afvinking zet een onbetaalde factuur op betaald en
stopt de opvolging: afvinken bij precies EEN open, herinnerde of geescaleerde vordering waarvan het factuurnummer als
LOSSE term in de omschrijving staat (hoofdletterongevoelig) en waarvan bedrag en valuta gelijk zijn. In alle andere
gevallen niet: een afwijkend bedrag, twee mogelijke facturen, geen factuurnummer, een nummer dat maar een deel is van
een ander woord. Een bijschrijving waarvan precies een BETAALDE vordering matcht is `al_afgevinkt` (zo vinkt een tweede
keer hetzelfde afschrift inlezen niets dubbel af); alles anders is `niet_gekoppeld`.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.core.services.bankafschrift import Bijschrijving, Vordering, koppel, lees_camt053

VOORBEELD = (
    Path(__file__).resolve().parents[2] / "fixtures" / "bankafschrift" / "camt053_voorbeeld.xml"
)


def _v(
    rij_id: int,
    nummer: str,
    bedrag: str = "100.00",
    status: str = "open",
    valuta: str = "EUR",
) -> Vordering:
    return Vordering(
        id=rij_id, factuurnummer=nummer, bedrag=Decimal(bedrag), valuta=valuta, status=status
    )


def _b(omschrijving: str, bedrag: str = "100.00", valuta: str = "EUR") -> Bijschrijving:
    return Bijschrijving(
        datum=date(2026, 10, 5),
        bedrag=Decimal(bedrag),
        valuta=valuta,
        omschrijving=omschrijving,
    )


class TestAfvinken:
    def test_number_and_amount_match_one_open_receivable(self) -> None:
        k = koppel(_b("Betaling F-2026-001"), [_v(1, "F-2026-001")])
        assert (k.uitkomst, k.vordering_id) == ("afvinken", 1)

    @pytest.mark.parametrize("status", ["open", "herinnerd", "geescaleerd"])
    def test_every_outstanding_status_can_be_ticked_off(self, status: str) -> None:
        assert koppel(_b("F-1"), [_v(1, "F-1", status=status)]).uitkomst == "afvinken"

    def test_the_same_amount_written_differently_matches(self) -> None:
        assert koppel(_b("F-1", "100"), [_v(1, "F-1", "100.00")]).uitkomst == "afvinken"

    def test_a_match_is_found_among_other_receivables(self) -> None:
        k = koppel(_b("F-2"), [_v(1, "F-1"), _v(2, "F-2"), _v(3, "F-3")])
        assert (k.uitkomst, k.vordering_id) == ("afvinken", 2)

    @pytest.mark.parametrize(
        "omschrijving",
        [
            "F-2026-001",
            "(F-2026-001)",
            "factuur F-2026-001.",
            "F-2026-001, bedankt",
            "ref:F-2026-001;",
            "f-2026-001",
            "F-2026-001/",
        ],
    )
    def test_a_number_as_a_separate_term_matches(self, omschrijving: str) -> None:
        assert koppel(_b(omschrijving), [_v(1, "F-2026-001")]).uitkomst == "afvinken"

    def test_regex_characters_in_a_number_are_taken_literally(self) -> None:
        assert koppel(_b("betaling F.1"), [_v(1, "F+1"), _v(2, "F.1")]).vordering_id == 2


class TestNietAfvinken:
    def test_a_different_amount_is_not_ticked_off(self) -> None:
        assert koppel(_b("F-1", "99.99"), [_v(1, "F-1")]).uitkomst == "niet_gekoppeld"

    def test_a_different_currency_is_not_ticked_off(self) -> None:
        assert koppel(_b("F-1", valuta="USD"), [_v(1, "F-1")]).uitkomst == "niet_gekoppeld"

    def test_two_possible_receivables_are_not_ticked_off(self) -> None:
        k = koppel(_b("F-1 en F-2"), [_v(1, "F-1"), _v(2, "F-2")])
        assert (k.uitkomst, k.vordering_id) == ("niet_gekoppeld", None)

    def test_the_same_number_on_two_receivables_is_not_ticked_off(self) -> None:
        assert koppel(_b("F-1"), [_v(1, "F-1"), _v(2, "F-1")]).uitkomst == "niet_gekoppeld"

    def test_a_text_without_a_number_is_not_matched(self) -> None:
        assert koppel(_b("Cadeau voor het team"), [_v(1, "F-1")]).uitkomst == "niet_gekoppeld"

    def test_an_empty_text_is_not_matched(self) -> None:
        assert koppel(_b(""), [_v(1, "F-1")]).uitkomst == "niet_gekoppeld"

    @pytest.mark.parametrize(
        "omschrijving",
        ["F-2026-0011", "xF-2026-001", "F-2026-0010 en nog iets", "F-2026-001x", "F-2026-0012"],
    )
    def test_a_number_that_is_part_of_another_word_does_not_match(self, omschrijving: str) -> None:
        assert koppel(_b(omschrijving), [_v(1, "F-2026-001")]).uitkomst == "niet_gekoppeld"

    @pytest.mark.parametrize("omschrijving", ["F-2026-001-2", "A-F-2026-001", "F-2026-001-X"])
    def test_a_number_inside_a_longer_dashed_number_does_not_match(self, omschrijving: str) -> None:
        assert koppel(_b(omschrijving), [_v(1, "F-2026-001")]).uitkomst == "niet_gekoppeld"

    def test_an_empty_invoice_number_never_matches(self) -> None:
        assert koppel(_b("iets"), [_v(1, "")]).uitkomst == "niet_gekoppeld"

    def test_no_receivables_at_all_is_not_matched(self) -> None:
        assert koppel(_b("F-1"), []).uitkomst == "niet_gekoppeld"


class TestNooitDubbel:
    def test_an_already_paid_receivable_is_reported_as_already_ticked_off(self) -> None:
        k = koppel(_b("F-1"), [_v(1, "F-1", status="betaald")])
        assert (k.uitkomst, k.vordering_id) == ("al_afgevinkt", 1)

    def test_a_paid_receivable_with_another_amount_is_not_matched(self) -> None:
        k = koppel(_b("F-1", "5.00"), [_v(1, "F-1", status="betaald")])
        assert k.uitkomst == "niet_gekoppeld"

    def test_an_open_match_next_to_a_paid_one_is_not_ticked_off(self) -> None:
        # Besluit na de acceptatie (2026-10-21): een bijschrijving die ook bij een al betaalde factuur past, kan voor
        # DIE factuur zijn. Een verkeerde afvinking stopt de opvolging van een onbetaalde factuur; bij twijfel niet.
        k = koppel(_b("F-1"), [_v(1, "F-1", status="betaald"), _v(2, "F-1")])
        assert (k.uitkomst, k.vordering_id) == ("niet_gekoppeld", None)

    def test_two_numbers_in_one_description_with_one_already_paid_is_not_ticked_off(self) -> None:
        # Het geval van de acceptant: "Facturen F-4 en F-5" (EUR 50), F-5 al met de hand op betaald gezet.
        k = koppel(
            _b("Facturen F-4 en F-5", "50.00"),
            [_v(4, "F-4", "50.00"), _v(5, "F-5", "50.00", status="betaald")],
        )
        assert (k.uitkomst, k.vordering_id) == ("niet_gekoppeld", None)

    def test_a_single_open_match_with_an_unrelated_paid_invoice_is_still_ticked_off(self) -> None:
        # Tegenproef: een betaalde factuur met een ander nummer maakt de bijschrijving niet dubbelzinnig.
        k = koppel(_b("F-4", "50.00"), [_v(4, "F-4", "50.00"), _v(5, "F-5", "50.00", status="betaald")])
        assert (k.uitkomst, k.vordering_id) == ("afvinken", 4)

    def test_two_paid_matches_are_not_reported_as_ticked_off(self) -> None:
        k = koppel(_b("F-1"), [_v(1, "F-1", status="betaald"), _v(2, "F-1", status="betaald")])
        assert k.uitkomst == "niet_gekoppeld"


class TestHetVoorbeeldafschrift:
    def test_the_example_statement_is_classified_as_agreed(self) -> None:
        vorderingen = [
            _v(1, "F-2026-001", "121.00"),
            _v(2, "F-2026-002", "250.00", "herinnerd"),
            _v(3, "F-2026-003", "100.00"),
            _v(4, "F-2026-004", "50.00"),
            _v(5, "F-2026-005", "50.00"),
            _v(6, "F-2026-006", "60.00", "geescaleerd"),
        ]
        bijschrijvingen = lees_camt053(VOORBEELD.read_bytes()).bijschrijvingen

        uitkomsten = [koppel(b, vorderingen).uitkomst for b in bijschrijvingen]

        assert uitkomsten == [
            "afvinken",
            "afvinken",
            "niet_gekoppeld",
            "niet_gekoppeld",
            "niet_gekoppeld",
            "afvinken",
            "afvinken",
        ]
