"""De veldenlaag haalt uit de TEKST van een bon of factuur de velden (bonlezer dag 1).

Brief `docs/agent-briefs/generated/2026-10-15-sprint-dag-bonlezer-dag1-testset-en-lezen.md`.
Deze tests draaien op tekst, zonder OCR en zonder Docling: ze meten de REGELS los van het lezen.
Het lezen zelf (OCR) staat in `scripts/bonlezer_meting.py` en `docs/evidence/bonlezer-meting-*.md`.

De testset (`tests/fixtures/bonnen/`) bevat per document de exacte brontekst (`*.tekst.txt`) en de
juiste antwoorden (`*.json`). Een regelfout op zuivere tekst is een fout in de veldenlaag; die moet
er hier uit. Wat pas na het lezen misgaat, hoort bij de meting.

Wat NIET wordt gezegd: dat de regels op ECHTE bonnen werken. De set is zelf gemaakt en daarom is
dit een ondergrens: een regel die hier faalt faalt zeker op echte bonnen, een regel die hier slaagt
is daar niet bewezen.
"""

from __future__ import annotations

import json
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.core.als.bonlezer.veldenlaag import lees_velden, parse_bedrag, parse_datum

SET = Path(__file__).resolve().parents[2] / "fixtures" / "bonnen"
DOCUMENTEN = sorted(p.name.removesuffix(".tekst.txt") for p in SET.glob("*.tekst.txt"))

BON = """\
BAKKERIJ DE GOUDEN KORST
Dorpsstraat 12, 1234 AB Voorbeeldstad
KvK 12345678  BTW NL123456789B01

Datum 15-10-2026  12:31
Bon 004521

Volkorenbrood 2x3,49  6,98
Tasje 1x0,25  0,25

TOTAAL  7,23
BTW 9%  0,58
BTW 21%  0,04
"""


class TestEenVasteBon:
    def test_the_total_is_read(self) -> None:
        assert lees_velden(BON).totaal == Decimal("7.23")

    def test_the_date_is_read_as_iso(self) -> None:
        assert lees_velden(BON).datum == date(2026, 10, 15)

    def test_vat_at_nine_percent_is_read(self) -> None:
        assert lees_velden(BON).btw[9] == Decimal("0.58")

    def test_vat_at_twenty_one_percent_is_read(self) -> None:
        assert lees_velden(BON).btw[21] == Decimal("0.04")

    def test_the_supplier_is_the_first_name_line(self) -> None:
        assert lees_velden(BON).leverancier == "BAKKERIJ DE GOUDEN KORST"

    def test_the_vat_number_and_chamber_of_commerce_number_are_read(self) -> None:
        velden = lees_velden(BON)

        assert (velden.btw_nummer, velden.kvk_nummer) == ("NL123456789B01", "12345678")


class TestBedragen:
    @pytest.mark.parametrize(
        ("tekst", "verwacht"),
        [
            ("1.234,56", "1234.56"),
            ("EUR 1.234,56", "1234.56"),
            ("12,50", "12.50"),
            ("0,05", "0.05"),
            ("12.50", "12.50"),
            ("1.234", "1234"),
            ("1,234.56", "1234.56"),
            ("  \u20ac 99,00 ", "99.00"),
            ("1.234.567,89", "1234567.89"),
        ],
    )
    def test_a_dutch_or_plain_amount_is_read(self, tekst: str, verwacht: str) -> None:
        assert parse_bedrag(tekst) == Decimal(verwacht)

    @pytest.mark.parametrize("tekst", ["", "abc", "12,5,0", "--"])
    def test_a_non_amount_is_none(self, tekst: str) -> None:
        assert parse_bedrag(tekst) is None


class TestDatums:
    @pytest.mark.parametrize(
        ("tekst", "verwacht"),
        [
            ("15-10-2026", date(2026, 10, 15)),
            ("15/10/2026", date(2026, 10, 15)),
            ("15.10.2026", date(2026, 10, 15)),
            ("2026-10-15", date(2026, 10, 15)),
            ("15 oktober 2026", date(2026, 10, 15)),
            ("1 maart 2026", date(2026, 3, 1)),
            ("15-10-26", date(2026, 10, 15)),
        ],
    )
    def test_the_common_dutch_notations_are_read(self, tekst: str, verwacht: date) -> None:
        assert parse_datum(tekst) == verwacht

    @pytest.mark.parametrize("tekst", ["31-02-2026", "15-13-2026", "geen datum", ""])
    def test_an_impossible_or_missing_date_is_none(self, tekst: str) -> None:
        assert parse_datum(tekst) is None


class TestBtwLayouts:
    def test_vat_with_the_base_before_the_amount(self) -> None:
        tekst = "TOTAAL 12,10\nBTW 21% over 10,00  2,10\n"

        assert lees_velden(tekst).btw == {21: Decimal("2.10")}

    def test_vat_in_a_table_with_net_vat_and_gross(self) -> None:
        tekst = "TOTAAL 109,00\nTarief  Netto  BTW  Bruto\n9%  100,00  9,00  109,00\n"

        assert lees_velden(tekst).btw == {9: Decimal("9.00")}

    def test_vat_where_ocr_glued_the_rate_to_the_word(self) -> None:
        """Gemeten in de meting: OCR las `BTW 9%` als `BTW9%`; een woordgrens zag dat niet als btw."""
        tekst = "Totaal te betalen 16,10\nBTW9% 1,33\n"

        assert lees_velden(tekst).btw == {9: Decimal("1.33")}

    def test_two_rates_on_one_document(self) -> None:
        tekst = "TOTAAL 12,10\nBTW 9%  0,50\nBTW 21%  1,60\n"

        assert lees_velden(tekst).btw == {9: Decimal("0.50"), 21: Decimal("1.60")}

    def test_the_subtotal_is_not_the_total(self) -> None:
        tekst = "Subtotaal excl. btw: EUR 100,00\nBTW 21%  21,00\nTotaal incl. btw: EUR 121,00\n"

        assert lees_velden(tekst).totaal == Decimal("121.00")

    def test_a_document_with_only_a_subtotal_has_no_total(self) -> None:
        assert lees_velden("Subtotaal 100,00\nBTW 21%  21,00\n").totaal is None

    def test_the_vat_amount_is_the_one_that_fits_the_rate_even_with_a_trailing_number(self) -> None:
        tekst = "TOTAAL 4,28\n21%  3,54  0,74  4,28  38,00\n"

        assert lees_velden(tekst).btw == {21: Decimal("0.74")}

    def test_the_total_of_the_vat_is_not_the_total(self) -> None:
        tekst = "Totaal BTW 21,00\nTotaal te betalen 121,00\n"

        assert lees_velden(tekst).totaal == Decimal("121.00")


class TestBtwnummerMetOcrSpaties:
    @pytest.mark.parametrize(
        "regel",
        [
            "KvK 06429764 BTW NL811 160913B03",
            "KvK 95734267 BTW NL2 15846996B03",
            "BTW NL 811160913 B 03",
            "BTW NL811160913B03",
        ],
    )
    def test_spaces_inside_the_number_are_ignored(self, regel: str) -> None:
        assert lees_velden(regel).btw_nummer in {
            "NL811160913B03",
            "NL215846996B03",
        }

    def test_the_spaces_are_removed_from_the_result(self) -> None:
        assert lees_velden("BTW NL811 160913B03").btw_nummer == "NL811160913B03"


class TestAndereOpmaak:
    """Opmaak die NIET uit de generator komt, zo geschreven zoals Nederlandse bonnen ze zetten.

    De testset hierboven is door dezelfde hand gemaakt als de regels; deze gevallen zijn er om de
    regels op te rekken buiten wat de generator zelf produceert.
    """

    def test_a_vat_table_with_a_header_and_columns(self) -> None:
        tekst = "SUBTOTAAL 25,64\nTOTAAL 25,64\nBTW  OVER  BTW\n9%  23,52  2,12\n"

        assert (lees_velden(tekst).totaal, lees_velden(tekst).btw) == (
            Decimal("25.64"),
            {9: Decimal("2.12")},
        )

    def test_a_total_in_brackets_and_a_vat_line_that_says_of_which(self) -> None:
        tekst = "Totaal (incl. BTW) \u20ac 242,00\nWaarvan BTW 21% \u20ac 42,00\n"

        assert (lees_velden(tekst).totaal, lees_velden(tekst).btw) == (
            Decimal("242.00"),
            {21: Decimal("42.00")},
        )

    def test_a_total_whose_amount_is_on_the_next_line(self) -> None:
        assert lees_velden("TOTAAL\n  12,34\n").totaal == Decimal("12.34")

    def test_a_date_with_a_time_after_it(self) -> None:
        assert lees_velden("Kassa 3  15-10-2026 12:31\nTOTAAL 1,00\n").datum == date(2026, 10, 15)

    def test_the_due_date_is_not_the_invoice_date(self) -> None:
        tekst = "Vervaldatum: 30-11-2026\nFactuurdatum: 15-10-2026\n"

        assert lees_velden(tekst).datum == date(2026, 10, 15)

    def test_a_discount_line_does_not_change_the_total(self) -> None:
        tekst = "Kortingskaart -1,50\nTOTAAL 10,00\n"

        assert lees_velden(tekst).totaal == Decimal("10.00")


class TestFactuurnummer:
    @pytest.mark.parametrize(
        "regel",
        [
            "Factuurnummer: 2026-665",
            "Factuurnr.: 2026-665",
            "Factuurnummer 2026-665",
            "Invoice number: 2026-665",
        ],
    )
    def test_the_invoice_number_is_read_after_its_label(self, regel: str) -> None:
        assert lees_velden(f"Leverancier BV\nFACTUUR\n{regel}\n").factuurnummer == "2026-665"

    def test_a_receipt_has_no_invoice_number(self) -> None:
        assert lees_velden(BON).factuurnummer is None


class TestOntbrekendeVelden:
    def test_an_empty_text_gives_empty_fields_and_no_error(self) -> None:
        velden = lees_velden("")

        assert (velden.totaal, velden.datum, velden.btw, velden.leverancier) == (
            None,
            None,
            {},
            None,
        )


@pytest.mark.parametrize("naam", DOCUMENTEN)
class TestDeTestsetOpZuiverdeTekst:
    """Elk document uit de set: de veldenlaag haalt uit de BRONTEKST precies de antwoorden."""

    def _laad(self, naam: str) -> tuple[str, dict[str, object]]:
        tekst = (SET / f"{naam}.tekst.txt").read_text(encoding="utf-8")
        antwoorden = json.loads((SET / f"{naam}.json").read_text(encoding="utf-8"))
        return tekst, antwoorden

    def test_total(self, naam: str) -> None:
        tekst, antwoorden = self._laad(naam)

        assert lees_velden(tekst).totaal == Decimal(str(antwoorden["totaal"]))

    def test_date(self, naam: str) -> None:
        tekst, antwoorden = self._laad(naam)
        gelezen = lees_velden(tekst).datum

        assert (gelezen.isoformat() if gelezen else None) == antwoorden["datum"]

    def test_vat_per_rate(self, naam: str) -> None:
        tekst, antwoorden = self._laad(naam)
        btw = antwoorden["btw"]
        assert isinstance(btw, dict)
        verwacht = {int(t): Decimal(b) for t, b in btw.items()}

        assert lees_velden(tekst).btw == verwacht

    def test_supplier(self, naam: str) -> None:
        tekst, antwoorden = self._laad(naam)
        gelezen = lees_velden(tekst).leverancier or ""

        assert gelezen.casefold() == str(antwoorden["leverancier"]).casefold()

    def test_invoice_number(self, naam: str) -> None:
        tekst, antwoorden = self._laad(naam)

        assert lees_velden(tekst).factuurnummer == antwoorden["factuurnummer"]

    def test_vat_and_chamber_numbers(self, naam: str) -> None:
        tekst, antwoorden = self._laad(naam)
        velden = lees_velden(tekst)

        assert (velden.btw_nummer, velden.kvk_nummer) == (
            antwoorden["btw_nummer"],
            antwoorden["kvk_nummer"],
        )


def test_the_testset_has_at_least_twenty_documents() -> None:
    assert len(DOCUMENTEN) >= 20


def test_every_document_has_an_image_or_pdf_and_answers() -> None:
    zonder = [
        n
        for n in DOCUMENTEN
        if not ((SET / f"{n}.pdf").exists() or (SET / f"{n}.jpg").exists())
        or not (SET / f"{n}.json").exists()
    ]

    assert zonder == []


class TestVijandigeInvoer:
    """Gate 2 (security, gemeten): `kvk` + 20.000 spaties kostte 7 s, 40.000 spaties 20 s.

    De tijd is CPU-tijd (`time.process_time`) en geen wandkloktijd (2026-10-26): `twintigduizend-regels`
    kost 0,2 s CPU, maar mat onder belasting 2,26 s wandklok (grens 1,5 s; los 3 keer groen), omdat de wandklok
    de wachttijd op een drukke machine meetelt. Een blow-up (7 s, 20 s) blijft zo zichtbaar.
    """

    @pytest.mark.parametrize(
        "tekst",
        [
            pytest.param("kvk" + " " * 40_000, id="kvk-spaties"),
            pytest.param("factuur nr" + " " * 40_000, id="factuurnr-spaties"),
            pytest.param("BTW 21% " + "1,00 " * 4000, id="btw-4000-bedragen"),
            pytest.param("TOTAAL " + "1,00 " * 5000, id="totaal-5000-bedragen"),
            pytest.param("a b " * 250_000, id="een-megabyte-op-een-regel"),
            pytest.param("1" * 100_000 + ",50", id="honderdduizend-cijfers"),
            pytest.param("\n".join(["TOTAAL 1,00"] * 20_000), id="twintigduizend-regels"),
        ],
    )
    def test_hostile_input_is_handled_quickly(self, tekst: str) -> None:
        start = time.process_time()

        lees_velden(tekst)

        assert time.process_time() - start < 1.5


class TestDeBedraggrensWerktOokZonderRegelafkapping:
    def test_the_amount_cap_alone_keeps_a_line_of_thousands_of_amounts_fast(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """De regelafkapping dekt dit al (500 tekens zijn ~100 bedragen); de grens is een tweede slot."""
        from src.core.als.bonlezer import veldenlaag

        monkeypatch.setattr(veldenlaag, "MAX_REGEL", 10_000_000)
        monkeypatch.setattr(veldenlaag, "MAX_TEKST", 10_000_000)
        start = time.process_time()

        lees_velden("BTW 21% " + "1,00 " * 4000)

        assert time.process_time() - start < 1.5


class TestDePatronenZijnZelfBegrensd:
    """De afkapping en `strip()` maskeren een onbegrensd patroon; hier staan ze uit of overbrugd.

    Gate 2 mat `kvk` + 20.000 spaties op 7 s. Een eindteken (`x`) houdt `strip()` buiten spel en een
    enorme `MAX_REGEL` zet de afkapping uit, zodat alleen het patroon zelf wordt getoetst.
    """

    @pytest.mark.parametrize(
        "tekst",
        [
            pytest.param("kvk" + " " * 40_000 + "x", id="kvk"),
            pytest.param("factuur nr" + " " * 40_000 + "x", id="factuurnr"),
            pytest.param("invoice number" + " " * 40_000 + "x", id="invoice"),
        ],
    )
    def test_a_long_run_of_spaces_after_a_label_is_handled_quickly(
        self, tekst: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.als.bonlezer import veldenlaag

        monkeypatch.setattr(veldenlaag, "MAX_REGEL", 10_000_000)
        monkeypatch.setattr(veldenlaag, "MAX_TEKST", 10_000_000)
        start = time.process_time()

        lees_velden(tekst)

        assert time.process_time() - start < 1.5


class TestBtwTerugval:
    def test_two_amounts_that_do_not_fit_the_rate_give_no_vat_instead_of_a_guess(self) -> None:
        assert lees_velden("BTW 21% 3,64 21,00\n").btw == {}

    def test_four_amounts_without_a_fit_give_no_vat(self) -> None:
        assert lees_velden("BTW 21% 1,00 2,00 3,00 4,00\n").btw == {}

    def test_a_table_row_with_only_one_amount_gives_no_vat(self) -> None:
        """Gemeten in de meting: `9% 2265 204 24,69` (komma's weg) gaf het BRUTO bedrag als btw."""
        assert lees_velden("TOTAAL 24,69\n9% 2265 204 24,69\n").btw == {}

    def test_a_vat_line_with_one_amount_is_still_read(self) -> None:
        assert lees_velden("BTW 9% 1,33\n").btw == {9: Decimal("1.33")}


class TestSpatieAlsDuizendtal:
    def test_a_space_thousands_amount_is_not_misread_as_its_remainder(self) -> None:
        """Gemeten (Gate 2): `1 234,56` werd `234.56`. Dubbelzinnig, dus liever niets dan fout."""
        assert lees_velden("Totaal incl. btw EUR 1 234,56\n").totaal is None

    def test_columns_of_amounts_separated_by_a_space_are_still_read(self) -> None:
        assert lees_velden("TOTAAL 4,28\n21%  3,54  0,74  4,28\n").btw == {21: Decimal("0.74")}


class TestNegatieveBedragen:
    def test_a_negative_total_keeps_its_sign(self) -> None:
        assert lees_velden("Totaal incl. btw -12,50\n").totaal == Decimal("-12.50")

    def test_a_negative_total_with_thousands_keeps_its_sign(self) -> None:
        assert lees_velden("Creditnota\nTOTAAL -1.234,56\n").totaal == Decimal("-1234.56")

    def test_an_invoice_number_with_a_hyphen_is_not_an_amount(self) -> None:
        assert lees_velden("Factuurnummer: 2026-665\nTOTAAL 1,00\n").totaal == Decimal("1.00")


class TestTotaalEnBuurregel:
    def test_a_total_label_without_amount_does_not_borrow_from_a_vat_line(self) -> None:
        tekst = "TOTAAL 29,30\nTotaal artikelen 3\nBTW 21% 5,08\n"

        assert lees_velden(tekst).totaal == Decimal("29.30")

    def test_a_total_line_is_not_a_vat_line(self) -> None:
        assert lees_velden("Totaal (incl. 21% BTW) 121,00\n").btw == {}


class TestLeverancierWoordgrens:
    @pytest.mark.parametrize(
        "naam", ["Paginabouw BV", "Factuurservice Noord BV", "Telefoonwinkel Zuid"]
    )
    def test_a_name_that_starts_with_a_label_word_is_still_a_supplier(self, naam: str) -> None:
        assert lees_velden(f"{naam}\nDorpsstraat 1, 1234 AB Plaats\n").leverancier == naam

    def test_a_name_that_starts_with_a_digit_is_a_supplier(self) -> None:
        tekst = "3 Broers Bakkerij\nDorpsstraat 1, 1234 AB Plaats\n"

        assert lees_velden(tekst).leverancier == "3 Broers Bakkerij"


class TestMaandAfkortingen:
    @pytest.mark.parametrize(
        ("tekst", "verwacht"),
        [
            ("15 okt 2026", date(2026, 10, 15)),
            ("15 okt. 2026", date(2026, 10, 15)),
            ("3 sept 2026", date(2026, 9, 3)),
            ("1 mrt 2026", date(2026, 3, 1)),
            ("20 dec 2026", date(2026, 12, 20)),
        ],
    )
    def test_common_abbreviations_are_read(self, tekst: str, verwacht: date) -> None:
        assert parse_datum(tekst) == verwacht


class TestBtwOverEenNettobedrag:
    """Gate 2 ronde 2: `BTW 21% over 100,00` met de btw weggevallen gaf het NETTO bedrag als btw."""

    @pytest.mark.parametrize(
        "regel",
        [
            "BTW 21% over 100,00",
            "BTW 9% netto 100,00",
            "BTW 21% grondslag 100,00",
            "BTW 0% over 50,00",
        ],
    )
    def test_a_base_without_a_vat_amount_gives_no_vat(self, regel: str) -> None:
        assert lees_velden(f"TOTAAL 121,00\n{regel}\n").btw == {}

    def test_a_base_with_its_vat_amount_is_still_read(self) -> None:
        tekst = "TOTAAL 121,00\nBTW 21% over 100,00  21,00\n"

        assert lees_velden(tekst).btw == {21: Decimal("21.00")}

    def test_zero_percent_with_zero_vat_is_read(self) -> None:
        assert lees_velden("TOTAAL 50,00\nBTW 0%  0,00\n").btw == {0: Decimal("0.00")}

    def test_zero_percent_with_a_non_zero_amount_gives_no_vat(self) -> None:
        assert lees_velden("TOTAAL 50,00\nBTW 0%  50,00\n").btw == {}


class TestNogTeBetalenIsNietHetTotaal:
    """Gate 2 ronde 2 (gemeten): `Nog te betalen 0,00` onder `Te betalen 121,00` gaf totaal 0,00."""

    @pytest.mark.parametrize(
        "extra",
        [
            "Nog te betalen 0,00",
            "Reeds te betalen 0,00",
            "Resterend totaal 0,00",
            "Openstaand totaal 0,00",
        ],
    )
    def test_a_remaining_amount_line_after_the_total_does_not_replace_it(self, extra: str) -> None:
        assert lees_velden(f"Te betalen 121,00\n{extra}\n").totaal == Decimal("121.00")

    def test_a_plain_total_is_still_read(self) -> None:
        assert lees_velden("Te betalen 121,00\n").totaal == Decimal("121.00")
