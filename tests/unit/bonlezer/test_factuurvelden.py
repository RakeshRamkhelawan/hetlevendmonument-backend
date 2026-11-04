"""De bonlezer leest ook de velden van een INKOOPFACTUUR: IBAN, vervaldatum en valuta (crediteuren dag 2, Keten F).

Brief `docs/agent-briefs/generated/2026-10-24-sprint-dag-crediteuren-dag2-inkoopfactuur-inlezen.md`. Dezelfde leespijplijn als
bij een bon (geen tweede), dus de nieuwe velden horen in drie plekken even streng te zijn: de veldenlaag (tekst -> veld), de
worker (veld -> JSON) en het schema van de backend (JSON -> toegestaan). Een veld dat niet te lezen is blijft `None`: de
veldenlaag raadt niet.

Wat NIET wordt gezegd: dat een echte PDF-factuur zo wordt gelezen. Dit draait op zuivere tekst; het lezen zelf is OCR.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from src.core.als.bonlezer.upload import _toets_velden
from src.core.als.bonlezer.veldenlaag import BonVelden, lees_velden
from src.core.als.bonlezer.worker import verwerk_opdracht

FACTUUR = """\
Drukkerij Van Dijk BV
Industrieweg 4, 3542 AB Utrecht
KvK 12345678  BTW NL123456789B01

FACTUUR
Factuurnummer: INK-2026-0042
Factuurdatum: 01-10-2026
Vervaldatum: 31-10-2026

Drukwerk flyers 500 stuks        EUR 1.000,00
BTW 21%                          EUR 210,00
Totaal incl. btw                 EUR 1.210,00

Betaal op IBAN NL91 ABNA 0417 1643 00 t.n.v. Drukkerij Van Dijk BV
"""


class TestDeVeldenlaagLeestDeFactuurvelden:
    def test_the_iban_is_read_without_spaces(self) -> None:
        assert lees_velden(FACTUUR).iban == "NL91ABNA0417164300"

    def test_the_due_date_is_read_and_is_not_the_invoice_date(self) -> None:
        velden = lees_velden(FACTUUR)

        assert (velden.datum, velden.vervaldatum) == (date(2026, 10, 1), date(2026, 10, 31))

    def test_the_currency_is_read_from_the_text(self) -> None:
        assert lees_velden(FACTUUR).valuta == "EUR"

    def test_an_iban_with_a_wrong_check_digit_is_not_read(self) -> None:
        tekst = FACTUUR.replace("NL91 ABNA 0417 1643 00", "NL92 ABNA 0417 1643 00")

        assert lees_velden(tekst).iban is None

    def test_a_text_without_an_iban_gives_none(self) -> None:
        assert lees_velden(FACTUUR.replace("IBAN NL91 ABNA 0417 1643 00", "")).iban is None

    def test_a_text_without_a_due_date_gives_none(self) -> None:
        assert lees_velden(FACTUUR.replace("Vervaldatum: 31-10-2026", "")).vervaldatum is None

    def test_a_text_without_a_currency_sign_gives_none(self) -> None:
        tekst = FACTUUR.replace("EUR ", "")

        assert lees_velden(tekst).valuta is None

    def test_the_new_fields_are_empty_for_a_plain_receipt(self) -> None:
        velden = lees_velden("BAKKERIJ DE GOUDEN KORST\nDatum 15-10-2026\nTotaal 6,98\n")

        assert (velden.iban, velden.vervaldatum) == (None, None)

    def test_the_default_of_the_dataclass_is_empty(self) -> None:
        assert BonVelden().iban is None


class TestDeWorkerGeeftDeFactuurvelden:
    class _Lezer:
        def lees(self, pad: Path) -> str:
            return FACTUUR

    def test_the_result_of_the_worker_carries_the_new_fields(self, tmp_path: Path) -> None:
        tenantmap = tmp_path / "7"
        tenantmap.mkdir()
        bestand_id = "a" * 32 + ".pdf"
        (tenantmap / bestand_id).write_bytes(b"%PDF-1.4 x")

        uitkomst = verwerk_opdracht(tmp_path, 7, bestand_id, lezer=self._Lezer())

        velden = uitkomst["velden"]
        assert isinstance(velden, dict)
        assert (velden["iban"], velden["vervaldatum"], velden["valuta"]) == (
            "NL91ABNA0417164300",
            "2026-10-31",
            "EUR",
        )


class TestHetSchemaVanDeBackendKentDeFactuurvelden:
    def test_the_new_fields_are_allowed(self) -> None:
        velden = {"iban": "NL91ABNA0417164300", "vervaldatum": "2026-10-31", "valuta": "EUR"}

        assert _toets_velden(velden) == velden

    def test_empty_new_fields_are_allowed(self) -> None:
        velden = {"iban": None, "vervaldatum": None, "valuta": None}

        assert _toets_velden(velden) == velden

    @pytest.mark.parametrize(
        ("sleutel", "waarde"),
        [
            ("iban", "NL91 ABNA 0417 1643 00"),
            ("iban", "x" * 40),
            ("iban", "nl91abna0417164300"),
            ("iban", 12345),
            ("vervaldatum", "31-10-2026"),
            ("vervaldatum", "2026-13-40"),
            ("valuta", "eur"),
            ("valuta", "EURO"),
        ],
    )
    def test_a_malformed_new_field_is_refused(self, sleutel: str, waarde: object) -> None:
        assert _toets_velden({sleutel: waarde}) is None


class TestKoppenOpEenRegelEnVerschillendeValuta:
    def test_two_dates_on_one_line_give_the_due_date_after_its_label(self) -> None:
        tekst = FACTUUR.replace(
            "Factuurdatum: 01-10-2026\nVervaldatum: 31-10-2026",
            "Factuurdatum 01-10-2026   Vervaldatum 31-10-2026",
        )

        velden = lees_velden(tekst)

        assert (velden.datum, velden.vervaldatum) == (date(2026, 10, 1), date(2026, 10, 31))

    def test_a_dollar_invoice_is_read_as_usd(self) -> None:
        tekst = FACTUUR.replace("EUR ", "USD ")

        assert lees_velden(tekst).valuta == "USD"

    def test_a_pound_sign_is_read_as_gbp(self) -> None:
        tekst = FACTUUR.replace("EUR ", "\u00a3 ")

        assert lees_velden(tekst).valuta == "GBP"

    def test_two_kinds_of_currency_signs_make_the_currency_uncertain(self) -> None:
        tekst = FACTUUR + "\nWisselkoers: 1 EUR = 1,08 USD\n"

        assert lees_velden(tekst).valuta is None
