"""Acceptatie dag 4: "Controleren" verscheen nooit en de lijst toonde alleen tijdstip en status.

Gemeten op de acceptatie-opstelling (2026-10-17): bon_12 gaf een foute leverancier en een LEGE btw-nummer en
KvK, zonder waarschuwing. Nu geeft een leeg btw-nummer of KvK, een leeg of ongeldig verplicht veld en btw die
groter is dan het totaal een melding "controleren". Dat is een AANWIJZING voor de medewerker: alleen een leeg
verplicht veld of een ongeldige vorm blokkeert het bevestigen (`controleer_velden`); een kassabon zonder KvK
mag na controle gewoon bevestigd worden.

De lijst toont per bon de oorspronkelijke bestandsnaam (veilig: zonder pad en zonder stuurtekens, begrensd), de
leverancier (uit de bevestiging, anders uit het leesresultaat), de stand en of er gecontroleerd moet worden.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from dramatiq.results import ResultMissing

from src.core.als.bonlezer import upload as upload_module
from src.core.als.bonlezer.bevestiging import BonBevestiging, moet_gecontroleerd
from src.core.als.bonlezer.upload import VERLOOP_SECONDEN, BonDienst, UploadFout

PDF = b"%PDF-1.4\n% een proefbestand\n"
START = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)
GOED: dict[str, object] = {
    "leverancier": "Bakkerij De Korenaar B.V.",
    "datum": "2026-10-01",
    "totaal": "12.10",
    "factuurnummer": "F-2026-001",
    "btw": {"9": "0.50", "21": "1.60"},
    "btw_nummer": "NL123456789B01",
    "kvk_nummer": "12345678",
}


class _Opstelling:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.nu = START
        self.resultaten: dict[str, dict[str, object]] = {}
        self.teller = 0
        self.dienst = BonDienst(root, verstuur=self._verstuur, haal=self._haal, nu=lambda: self.nu)
        self.bevestiging = BonBevestiging(root, nu=lambda: self.nu)

    def _verstuur(self, tenant_id: int, bestand_id: str) -> str:
        self.teller += 1
        return f"bericht-{self.teller}"

    def _haal(self, message_id: str) -> dict[str, object]:
        if message_id not in self.resultaten:
            raise ResultMissing(message_id)  # type: ignore[call-arg]
        return self.resultaten[message_id]

    def bon(
        self,
        velden: dict[str, object] | None = None,
        *,
        tenant: int = 1,
        naam: str = "bon.pdf",
        status: str = "gelezen",
        lees: bool = True,
    ) -> str:
        bestand_id = self.dienst.uploaden(tenant, naam, PDF)
        self.resultaten[f"bericht-{self.teller}"] = {
            "status": status,
            "reden": "" if status == "gelezen" else "kon niet",
            "sha256": hashlib.sha256(PDF).hexdigest(),
            "velden": dict(velden if velden is not None else GOED),
        }
        if lees:
            self.dienst.status(tenant, bestand_id)
        return bestand_id

    def lijst(self, tenant: int = 1, **kw: object) -> list[dict[str, object]]:
        items, _ = self.bevestiging.lijst(tenant, limit=50, offset=0, **kw)  # type: ignore[arg-type]
        return items


@pytest.fixture
def o(tmp_path: Path) -> _Opstelling:
    return _Opstelling(tmp_path)


class TestWatGecontroleerdMoetWorden:
    def test_a_valid_bon_has_no_remarks(self) -> None:
        assert moet_gecontroleerd(dict(GOED)) == {}

    def test_an_empty_vat_number_is_flagged(self) -> None:
        assert moet_gecontroleerd({**GOED, "btw_nummer": None}) == {"btw_nummer": "controleren"}

    def test_an_empty_chamber_number_is_flagged(self) -> None:
        assert moet_gecontroleerd({**GOED, "kvk_nummer": ""}) == {"kvk_nummer": "controleren"}

    def test_a_missing_vat_and_chamber_number_are_both_flagged(self) -> None:
        velden = {k: v for k, v in GOED.items() if k not in ("btw_nummer", "kvk_nummer")}

        assert set(moet_gecontroleerd(velden)) == {"btw_nummer", "kvk_nummer"}

    @pytest.mark.parametrize("veld", ["leverancier", "datum", "totaal"])
    def test_an_empty_required_field_is_flagged(self, veld: str) -> None:
        assert veld in moet_gecontroleerd({**GOED, veld: None})

    def test_an_invalid_vat_number_is_flagged(self) -> None:
        assert moet_gecontroleerd({**GOED, "btw_nummer": "NL12B01"}) == {
            "btw_nummer": "controleren"
        }

    def test_vat_larger_than_the_total_flags_the_total(self) -> None:
        velden = {**GOED, "totaal": "1.00", "btw": {"21": "1.60"}}

        assert moet_gecontroleerd(velden) == {"totaal": "controleren"}

    def test_vat_equal_to_the_total_is_not_flagged(self) -> None:
        velden = {**GOED, "totaal": "2.10", "btw": {"9": "0.50", "21": "1.60"}}

        assert moet_gecontroleerd(velden) == {}

    def test_a_credit_note_with_matching_negative_vat_is_not_flagged(self) -> None:
        """Gate 2 (code): bij een creditnota is btw -21 groter dan totaal -121 alleen als je het teken meetelt."""
        velden = {**GOED, "totaal": "-121.00", "btw": {"21": "-21.00"}}

        assert moet_gecontroleerd(velden) == {}

    def test_a_credit_note_with_vat_larger_than_the_total_is_flagged(self) -> None:
        velden = {**GOED, "totaal": "-1.00", "btw": {"21": "-50.00"}}

        assert moet_gecontroleerd(velden) == {"totaal": "controleren"}

    def test_a_bon_without_vat_amounts_is_not_flagged_for_the_total(self) -> None:
        assert moet_gecontroleerd({**GOED, "btw": {}}) == {}


class TestHetDetailToontWatGecontroleerdMoetWorden:
    def test_the_detail_of_a_bon_without_vat_and_chamber_number_names_both(
        self, o: _Opstelling
    ) -> None:
        velden = {**GOED, "leverancier": "Bloemgracht", "btw_nummer": None, "kvk_nummer": None}
        bestand_id = o.bon(velden, lees=False)

        verrijkt = o.bevestiging.verrijk(1, bestand_id, o.dienst.status(1, bestand_id))

        assert set(verrijkt["controleren"]) == {"btw_nummer", "kvk_nummer"}  # type: ignore[arg-type]

    def test_such_a_bon_can_still_be_confirmed(self, o: _Opstelling) -> None:
        velden = {**GOED, "btw_nummer": None, "kvk_nummer": None}
        bestand_id = o.bon(velden)

        record = o.bevestiging.bevestig(1, bestand_id, velden, gebruiker_id=3)

        assert record["door"] == 3

    def test_an_invalid_vat_number_still_blocks_the_confirmation(self, o: _Opstelling) -> None:
        bestand_id = o.bon()

        with pytest.raises(UploadFout) as fout:
            o.bevestiging.bevestig(1, bestand_id, {**GOED, "btw_nummer": "x"}, gebruiker_id=3)

        assert fout.value.status_code == 422


class TestDeLijstToontMeer:
    def test_the_original_file_name_is_shown(self, o: _Opstelling) -> None:
        o.bon(naam="bon_12.jpg.pdf")

        assert o.lijst()[0]["naam"] == "bon_12.jpg.pdf"

    def test_a_path_in_the_file_name_is_dropped(self, o: _Opstelling) -> None:
        o.bon(naam="C:\\fakepath\\mijn\\factuur.pdf")
        o.bon(naam="../../etc/passwd.pdf")

        assert sorted(str(i["naam"]) for i in o.lijst()) == ["factuur.pdf", "passwd.pdf"]

    def test_control_characters_are_removed_from_the_file_name(self, o: _Opstelling) -> None:
        o.bon(naam="fac\u202etuur\x00\u200b.pdf")

        assert o.lijst()[0]["naam"] == "factuur.pdf"

    def test_the_file_name_is_cut_at_120_characters(self, o: _Opstelling) -> None:
        o.bon(naam="a" * 300 + ".pdf")

        assert len(str(o.lijst()[0]["naam"])) <= 120

    def test_a_file_name_with_html_is_kept_as_plain_text(self, o: _Opstelling) -> None:
        o.bon(naam="<img src=x onerror=alert(1)>.pdf")

        assert o.lijst()[0]["naam"] == "<img src=x onerror=alert(1)>.pdf"

    def test_the_supplier_comes_from_the_read_result(self, o: _Opstelling) -> None:
        o.bon()

        assert o.lijst()[0]["leverancier"] == "Bakkerij De Korenaar B.V."

    def test_the_supplier_of_a_confirmed_bon_comes_from_the_confirmation(
        self, o: _Opstelling
    ) -> None:
        bestand_id = o.bon()
        o.bevestiging.bevestig(
            1, bestand_id, {**GOED, "leverancier": "Gecorrigeerd B.V."}, gebruiker_id=1
        )

        assert o.lijst()[0]["leverancier"] == "Gecorrigeerd B.V."

    def test_control_characters_are_removed_from_the_supplier(self, o: _Opstelling) -> None:
        o.bon({**GOED, "leverancier": "Bak\u202ekerij\x00"})

        assert o.lijst()[0]["leverancier"] == "Bakkerij"

    def test_a_bon_without_a_result_has_no_supplier(self, o: _Opstelling) -> None:
        o.dienst.uploaden(1, "a.pdf", PDF)

        assert o.lijst()[0]["leverancier"] is None

    def test_an_unconfirmed_bon_with_remarks_is_flagged_in_the_list(self, o: _Opstelling) -> None:
        o.bon({**GOED, "btw_nummer": None, "kvk_nummer": None, "leverancier": "Bloemgracht"})

        assert o.lijst()[0]["controleren"] is True

    def test_a_clean_bon_is_not_flagged_in_the_list(self, o: _Opstelling) -> None:
        o.bon()

        assert o.lijst()[0]["controleren"] is False

    def test_a_confirmed_bon_is_not_flagged(self, o: _Opstelling) -> None:
        velden = {**GOED, "btw_nummer": None, "kvk_nummer": None}
        bestand_id = o.bon(velden)
        o.bevestiging.bevestig(1, bestand_id, velden, gebruiker_id=1)

        assert o.lijst()[0]["controleren"] is False

    def test_the_state_of_a_read_bon_is_read(self, o: _Opstelling) -> None:
        o.bon()

        assert o.lijst()[0]["status"] == "gelezen"

    def test_the_state_of_a_refused_bon_is_refused(self, o: _Opstelling) -> None:
        o.bon(status="geweigerd")

        assert o.lijst()[0]["status"] == "geweigerd"

    def test_the_state_of_a_bon_without_a_result_yet_is_waiting(self, o: _Opstelling) -> None:
        o.dienst.uploaden(1, "a.pdf", PDF)

        assert o.lijst()[0]["status"] == "wachten"

    def test_the_state_of_an_old_bon_without_any_result_is_expired(self, o: _Opstelling) -> None:
        o.dienst.uploaden(1, "a.pdf", PDF)
        o.nu = START + timedelta(seconds=VERLOOP_SECONDEN + 1)

        assert o.lijst()[0]["status"] == "verlopen"

    def test_another_tenant_sees_nothing_of_these_bonnen(self, o: _Opstelling) -> None:
        o.bon()

        assert o.lijst(tenant=2) == []

    def test_the_list_still_says_whether_a_bon_is_confirmed(self, o: _Opstelling) -> None:
        bestand_id = o.bon()
        o.bevestiging.bevestig(1, bestand_id, dict(GOED), gebruiker_id=1)

        assert o.lijst()[0]["bevestigd"] is True


class TestDeLijstHaaltOntbrekendeResultatenOp:
    """Een bon die niemand heeft geopend heeft nog geen vastgelegd resultaat; de lijst haalt dat op."""

    def test_a_bon_without_a_stored_result_is_refreshed(self, o: _Opstelling) -> None:
        o.bon(lees=False)
        opgehaald: list[str] = []

        def _ververs(bestand_id: str) -> None:
            opgehaald.append(bestand_id)
            o.dienst.status(1, bestand_id)

        items = o.lijst(ververs=_ververs)

        assert (len(opgehaald), items[0]["status"], items[0]["leverancier"]) == (
            1,
            "gelezen",
            "Bakkerij De Korenaar B.V.",
        )

    def test_a_bon_with_a_stored_result_is_not_refreshed(self, o: _Opstelling) -> None:
        o.bon()
        opgehaald: list[str] = []

        o.lijst(ververs=opgehaald.append)

        assert opgehaald == []

    def test_a_confirmed_bon_is_not_refreshed(self, o: _Opstelling) -> None:
        bestand_id = o.bon(lees=False)
        o.bevestiging.bevestig(1, bestand_id, dict(GOED), gebruiker_id=1)
        opgehaald: list[str] = []

        o.lijst(ververs=opgehaald.append)

        assert opgehaald == []

    def test_an_old_bon_whose_result_is_still_in_redis_is_refreshed(self, o: _Opstelling) -> None:
        """Code-review: het resultaat staat 30 dagen in Redis; een bon die pas na de lunch wordt bekeken moet
        ook nog gelezen worden, niet alleen tijdens de eerste 8 minuten."""
        o.bon(lees=False)
        o.nu = START + timedelta(seconds=VERLOOP_SECONDEN + 3600)

        def _ververs(bestand_id: str) -> None:
            o.dienst.status(1, bestand_id)

        items = o.lijst(ververs=_ververs)

        assert (items[0]["status"], items[0]["leverancier"]) == (
            "gelezen",
            "Bakkerij De Korenaar B.V.",
        )

    def test_an_old_bon_without_a_result_anywhere_is_expired(self, o: _Opstelling) -> None:
        o.dienst.uploaden(1, "a.pdf", PDF)
        o.nu = START + timedelta(seconds=VERLOOP_SECONDEN + 1)

        items = o.lijst(ververs=lambda bestand_id: o.dienst.status(1, bestand_id) and None)

        assert items[0]["status"] == "verlopen"

    def test_the_refreshing_stops_after_the_first_failure_in_one_request(
        self, o: _Opstelling, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(upload_module, "MAX_OPENSTAAND", 100)
        for _ in range(5):
            o.dienst.uploaden(1, "a.pdf", PDF)
            o.nu += timedelta(seconds=1)
        pogingen: list[str] = []

        def _stuk(bestand_id: str) -> None:
            pogingen.append(bestand_id)
            raise RuntimeError("redis weg")

        o.lijst(ververs=_stuk)

        assert len(pogingen) == 1

    def test_at_most_20_bonnen_are_refreshed_per_request(
        self, o: _Opstelling, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(upload_module, "MAX_OPENSTAAND", 100)
        for _ in range(25):
            o.dienst.uploaden(1, "a.pdf", PDF)
            o.nu += timedelta(seconds=1)
        opgehaald: list[str] = []

        o.lijst(ververs=opgehaald.append)

        assert len(opgehaald) == 20

    def test_a_failing_refresh_does_not_break_the_list(self, o: _Opstelling) -> None:
        o.bon(lees=False)

        def _stuk(bestand_id: str) -> None:
            raise RuntimeError("redis weg")

        assert len(o.lijst(ververs=_stuk)) == 1
