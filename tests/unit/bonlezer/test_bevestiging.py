"""Bonlezer dag 4: velden controleren, corrigeren en bevestigen; veilig tonen en exporteren.

Brief `docs/agent-briefs/generated/2026-10-17-sprint-dag-bonlezer-dag4-scherm-bevestigen-en-30-dagen.md`.
Alles wat uit een bon komt is onbetrouwbaar (de worker leest hem met een parser die vijandige invoer krijgt):
btw-nummer en KvK-nummer worden strak getoetst ("controleren" bij twijfel), tekst wordt van stuurtekens
ontdaan, en in een CSV krijgt een cel die met een formuleteken begint een apostrof ervoor. Een bevestiging
gaat in een apart bestand naast de bon (`<bestand_id>.bevestigd.json`, geen tabel) dat de opruiming na 30
dagen NIET aanraakt.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.core.als.bonlezer.bevestiging import (
    BonBevestiging,
    controleer_velden,
    csv_veilig,
    schoon_tekst,
)
from src.core.als.bonlezer.upload import BonDienst, BonNietGevonden, UploadFout

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
        self.dienst = BonDienst(
            root, verstuur=lambda t, b: "bericht", haal=lambda m: {}, nu=lambda: self.nu
        )
        self.bevestiging = BonBevestiging(root, nu=lambda: self.nu)

    def bon(self, tenant_id: int = 1) -> str:
        return self.dienst.uploaden(tenant_id, "a.pdf", PDF)


@pytest.fixture
def o(tmp_path: Path) -> _Opstelling:
    return _Opstelling(tmp_path)


class TestControleerVelden:
    def test_valid_fields_have_no_remarks(self) -> None:
        assert controleer_velden(dict(GOED)) == {}

    @pytest.mark.parametrize(
        "btw_nummer",
        [
            "NL12345678B01",
            "NL1234567890B01",
            "nl123456789b01",
            "NL123456789B1",
            "BE123456789B01",
            "x",
            " NL123456789B01",
        ],
    )
    def test_a_wrong_vat_number_is_to_be_checked(self, btw_nummer: str) -> None:
        assert controleer_velden({**GOED, "btw_nummer": btw_nummer}) == {
            "btw_nummer": "controleren"
        }

    @pytest.mark.parametrize("kvk", ["1234567", "123456789", "abcdefgh", "1234 5678", "12345678\n"])
    def test_a_wrong_chamber_of_commerce_number_is_to_be_checked(self, kvk: str) -> None:
        assert controleer_velden({**GOED, "kvk_nummer": kvk}) == {"kvk_nummer": "controleren"}

    @pytest.mark.parametrize("veld", ["btw_nummer", "kvk_nummer"])
    def test_an_empty_vat_or_chamber_number_is_allowed(self, veld: str) -> None:
        assert controleer_velden({**GOED, veld: None}) == {}

    @pytest.mark.parametrize("veld", ["leverancier", "datum", "totaal"])
    def test_a_missing_main_field_is_to_be_checked(self, veld: str) -> None:
        assert controleer_velden({**GOED, veld: None}) == {veld: "controleren"}

    def test_an_empty_text_is_the_same_as_missing(self) -> None:
        assert controleer_velden({**GOED, "leverancier": "   "}) == {"leverancier": "controleren"}

    def test_several_problems_are_all_reported(self) -> None:
        velden = {**GOED, "btw_nummer": "x", "kvk_nummer": "y", "totaal": None}

        assert set(controleer_velden(velden)) == {"btw_nummer", "kvk_nummer", "totaal"}


class TestSchoonTekst:
    @pytest.mark.parametrize(
        ("invoer", "uitvoer"),
        [
            ("Bakker\x00ij", "Bakkerij"),
            ("regel\neen", "regeleen"),
            ("a\u202eb", "ab"),
            ("a\u2066b\u2069", "ab"),
            ("a\u200bb", "ab"),
            ("gewone tekst", "gewone tekst"),
            ("<script>alert(1)</script>", "<script>alert(1)</script>"),
        ],
    )
    def test_control_characters_are_removed_and_text_is_kept(
        self, invoer: str, uitvoer: str
    ) -> None:
        assert schoon_tekst(invoer) == uitvoer


class TestCsvVeilig:
    @pytest.mark.parametrize("formule", ["=SUM(A1)", "+1+1", "-2+3", "@SUM(A1)"])
    def test_a_cell_that_starts_like_a_formula_gets_an_apostrophe(self, formule: str) -> None:
        assert csv_veilig(formule).startswith("'")

    def test_the_formula_text_is_kept(self) -> None:
        assert csv_veilig("=SUM(A1)") == "'=SUM(A1)"

    def test_normal_text_is_unchanged(self) -> None:
        assert csv_veilig("Bakkerij De Korenaar") == "Bakkerij De Korenaar"

    def test_a_vendor_that_merely_contains_an_equals_sign_is_unchanged(self) -> None:
        assert csv_veilig("A=B Beheer") == "A=B Beheer"

    def test_control_characters_are_removed_first(self) -> None:
        assert csv_veilig("\x00=1") == "'=1"

    def test_a_tab_or_return_in_front_of_a_formula_does_not_hide_it(self) -> None:
        assert csv_veilig("\t=1") == "'=1"


class TestBevestigen:
    def test_a_confirmation_is_stored_next_to_the_bon(self, o: _Opstelling) -> None:
        bestand_id = o.bon()

        o.bevestiging.bevestig(1, bestand_id, dict(GOED), gebruiker_id=42)

        assert (o.root / "1" / f"{bestand_id}.bevestigd.json").exists()

    def test_the_confirmation_records_who_and_when(self, o: _Opstelling) -> None:
        bestand_id = o.bon()

        o.bevestiging.bevestig(1, bestand_id, dict(GOED), gebruiker_id=42)

        opgeslagen = json.loads(
            (o.root / "1" / f"{bestand_id}.bevestigd.json").read_text(encoding="utf-8")
        )
        assert (opgeslagen["door"], opgeslagen["bevestigd_op"]) == (42, START.isoformat())

    def test_the_corrected_fields_are_what_is_stored(self, o: _Opstelling) -> None:
        bestand_id = o.bon()

        o.bevestiging.bevestig(1, bestand_id, {**GOED, "totaal": "99.00"}, gebruiker_id=1)

        assert o.bevestiging.bevestigd(1, bestand_id)["velden"]["totaal"] == "99.00"  # type: ignore[index]

    def test_text_fields_are_cleaned_when_stored(self, o: _Opstelling) -> None:
        bestand_id = o.bon()

        o.bevestiging.bevestig(
            1, bestand_id, {**GOED, "leverancier": "Bak\u202eker\x00ij"}, gebruiker_id=1
        )

        assert o.bevestiging.bevestigd(1, bestand_id)["velden"]["leverancier"] == "Bakkerij"  # type: ignore[index]

    def test_html_in_a_field_is_stored_as_plain_text(self, o: _Opstelling) -> None:
        bestand_id = o.bon()

        o.bevestiging.bevestig(1, bestand_id, {**GOED, "leverancier": "<b>X</b>"}, gebruiker_id=1)

        assert o.bevestiging.bevestigd(1, bestand_id)["velden"]["leverancier"] == "<b>X</b>"  # type: ignore[index]

    def test_fields_to_be_checked_are_refused(self, o: _Opstelling) -> None:
        bestand_id = o.bon()

        with pytest.raises(UploadFout) as fout:
            o.bevestiging.bevestig(1, bestand_id, {**GOED, "btw_nummer": "x"}, gebruiker_id=1)

        assert (fout.value.status_code, "btw_nummer" in fout.value.boodschap) == (422, True)

    def test_nothing_is_stored_when_the_fields_are_refused(self, o: _Opstelling) -> None:
        bestand_id = o.bon()

        with pytest.raises(UploadFout):
            o.bevestiging.bevestig(1, bestand_id, {**GOED, "kvk_nummer": "1"}, gebruiker_id=1)

        assert o.bevestiging.bevestigd(1, bestand_id) is None

    def test_fields_outside_the_schema_are_refused(self, o: _Opstelling) -> None:
        bestand_id = o.bon()

        with pytest.raises(UploadFout):
            o.bevestiging.bevestig(1, bestand_id, {**GOED, "onbekend": "x"}, gebruiker_id=1)

    def test_another_tenant_cannot_confirm_the_bon(self, o: _Opstelling) -> None:
        bestand_id = o.bon(1)

        with pytest.raises(BonNietGevonden):
            o.bevestiging.bevestig(2, bestand_id, dict(GOED), gebruiker_id=1)

    def test_an_unknown_bon_cannot_be_confirmed(self, o: _Opstelling) -> None:
        with pytest.raises(BonNietGevonden):
            o.bevestiging.bevestig(1, "0" * 32 + ".pdf", dict(GOED), gebruiker_id=1)

    def test_a_path_in_the_id_is_not_found(self, o: _Opstelling) -> None:
        bestand_id = o.bon(2)

        with pytest.raises(BonNietGevonden):
            o.bevestiging.bevestig(1, f"../2/{bestand_id}", dict(GOED), gebruiker_id=1)

    def test_a_second_confirmation_replaces_the_first(self, o: _Opstelling) -> None:
        bestand_id = o.bon()
        o.bevestiging.bevestig(1, bestand_id, dict(GOED), gebruiker_id=1)

        o.bevestiging.bevestig(1, bestand_id, {**GOED, "totaal": "5.00"}, gebruiker_id=2)

        antwoord = o.bevestiging.bevestigd(1, bestand_id)
        assert (antwoord["velden"]["totaal"], antwoord["door"]) == ("5.00", 2)  # type: ignore[index]

    def test_a_confirmed_bon_no_longer_counts_as_waiting(self, o: _Opstelling) -> None:
        bestand_id = o.bon()

        o.bevestiging.bevestig(1, bestand_id, dict(GOED), gebruiker_id=1)

        meta = json.loads((o.root / "1" / f"{bestand_id}.meta.json").read_text(encoding="utf-8"))
        assert meta["afgerond"] is True

    def test_a_confirmation_leaves_no_temporary_file_behind(self, o: _Opstelling) -> None:
        bestand_id = o.bon()

        o.bevestiging.bevestig(1, bestand_id, dict(GOED), gebruiker_id=1)

        assert [p for p in (o.root / "1").iterdir() if p.name.endswith(".tmp")] == []

    def test_an_unconfirmed_bon_has_no_confirmation(self, o: _Opstelling) -> None:
        assert o.bevestiging.bevestigd(1, o.bon()) is None

    def test_the_confirmation_of_another_tenant_is_not_shown(self, o: _Opstelling) -> None:
        bestand_id = o.bon(1)
        o.bevestiging.bevestig(1, bestand_id, dict(GOED), gebruiker_id=1)

        assert o.bevestiging.bevestigd(2, bestand_id) is None


class TestLijst:
    def test_the_list_shows_the_own_bonnen_newest_first(self, o: _Opstelling) -> None:
        eerste = o.bon()
        o.nu = START + timedelta(minutes=5)
        tweede = o.bon()

        items, totaal = o.bevestiging.lijst(1, limit=50, offset=0)

        assert ([i["bestand_id"] for i in items], totaal) == ([tweede, eerste], 2)

    def test_the_list_does_not_show_another_tenant(self, o: _Opstelling) -> None:
        o.bon(1)
        o.bon(2)

        _, totaal = o.bevestiging.lijst(1, limit=50, offset=0)

        assert totaal == 1

    def test_the_list_marks_a_confirmed_bon(self, o: _Opstelling) -> None:
        bestand_id = o.bon()
        o.bevestiging.bevestig(1, bestand_id, dict(GOED), gebruiker_id=1)

        items, _ = o.bevestiging.lijst(1, limit=50, offset=0)

        assert items[0]["bevestigd"] is True

    def test_the_list_marks_an_unconfirmed_bon_as_not_confirmed(self, o: _Opstelling) -> None:
        o.bon()

        items, _ = o.bevestiging.lijst(1, limit=50, offset=0)

        assert items[0]["bevestigd"] is False

    def test_the_list_is_paged(self, o: _Opstelling) -> None:
        for minuut in range(3):
            o.nu = START + timedelta(minutes=minuut)
            o.bon()

        items, totaal = o.bevestiging.lijst(1, limit=2, offset=2)

        assert (len(items), totaal) == (1, 3)

    def test_the_list_never_contains_the_hash_or_the_message_id(self, o: _Opstelling) -> None:
        o.bon()

        items, _ = o.bevestiging.lijst(1, limit=50, offset=0)

        # Sinds de acceptatie van dag 4 ook naam, stand, leverancier en controleren; nooit hash of bericht-id.
        assert set(items[0]) == {
            "bestand_id",
            "aangemaakt",
            "bevestigd",
            "naam",
            "status",
            "leverancier",
            "controleren",
        }

    def test_an_empty_tenant_has_an_empty_list(self, o: _Opstelling) -> None:
        assert o.bevestiging.lijst(9, limit=50, offset=0) == ([], 0)


class TestExport:
    @staticmethod
    def _rijen(tekst: str) -> list[dict[str, str]]:
        return list(csv.DictReader(io.StringIO(tekst)))

    def test_only_confirmed_bonnen_are_exported(self, o: _Opstelling) -> None:
        o.bon()
        bevestigd = o.bon()
        o.bevestiging.bevestig(1, bevestigd, dict(GOED), gebruiker_id=1)

        assert len(self._rijen(o.bevestiging.csv_export(1))) == 1

    def test_another_tenant_is_not_exported(self, o: _Opstelling) -> None:
        andere = o.bon(2)
        o.bevestiging.bevestig(2, andere, dict(GOED), gebruiker_id=1)

        assert self._rijen(o.bevestiging.csv_export(1)) == []

    def test_a_formula_in_a_field_is_neutralised_in_the_csv(self, o: _Opstelling) -> None:
        bestand_id = o.bon()
        o.bevestiging.bevestig(1, bestand_id, {**GOED, "leverancier": "=SUM(A1)"}, gebruiker_id=1)

        assert self._rijen(o.bevestiging.csv_export(1))[0]["leverancier"] == "'=SUM(A1)"

    def test_a_negative_total_stays_a_number(self, o: _Opstelling) -> None:
        bestand_id = o.bon()
        o.bevestiging.bevestig(1, bestand_id, {**GOED, "totaal": "-5.00"}, gebruiker_id=1)

        assert self._rijen(o.bevestiging.csv_export(1))[0]["totaal"] == "-5.00"

    def test_the_vat_per_rate_is_in_its_own_columns(self, o: _Opstelling) -> None:
        bestand_id = o.bon()
        o.bevestiging.bevestig(1, bestand_id, dict(GOED), gebruiker_id=1)

        rij = self._rijen(o.bevestiging.csv_export(1))[0]

        assert (rij["btw_9"], rij["btw_21"]) == ("0.50", "1.60")

    def test_the_header_is_present_for_an_empty_export(self, o: _Opstelling) -> None:
        assert o.bevestiging.csv_export(1).startswith("bestandsnaam,")


class TestSamenvatting:
    def test_the_summary_counts_the_confirmed_bonnen_and_sums_the_vat(self, o: _Opstelling) -> None:
        for _ in range(2):
            o.bevestiging.bevestig(1, o.bon(), dict(GOED), gebruiker_id=1)
        o.bon()  # niet bevestigd

        samenvatting = o.bevestiging.samenvatting(1)

        assert (samenvatting["aantal"], samenvatting["totaal"], samenvatting["btw"]) == (
            2,
            "24.20",
            {"9": "1.00", "21": "3.20"},
        )

    def test_the_summary_of_nothing_is_zero(self, o: _Opstelling) -> None:
        assert o.bevestiging.samenvatting(1) == {"aantal": 0, "totaal": "0.00", "btw": {}}

    def test_the_summary_leaves_out_another_tenant(self, o: _Opstelling) -> None:
        o.bevestiging.bevestig(2, o.bon(2), dict(GOED), gebruiker_id=1)

        assert o.bevestiging.samenvatting(1)["aantal"] == 0


class TestEenMisluktSchrijvenLaatNietsAchter:
    """Code- en security-review dag 4: een race met de opruiming of een schijffout mag geen rest achterlaten."""

    def test_a_failed_replace_leaves_no_temporary_file_with_the_fields(
        self, o: _Opstelling, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        bestand_id = o.bon()

        def _kapot(bron: object, doel: object) -> None:
            raise OSError("schijf vol")

        monkeypatch.setattr(os, "replace", _kapot)

        with pytest.raises(OSError):
            o.bevestiging.bevestig(1, bestand_id, dict(GOED), gebruiker_id=7)

        assert list((o.root / "1").glob("*.bevestigd.json*")) == []

    def test_a_bon_removed_by_the_cleanup_during_the_confirmation_leaves_no_orphan_metadata(
        self, o: _Opstelling, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bestand_id = o.bon()
        echte = BonBevestiging._markeer_afgerond

        def _na_opruiming(self: BonBevestiging, tenant_id: int, bid: str, meta: dict[str, object]) -> None:
            (o.root / str(tenant_id) / f"{bid}.meta.json").unlink()
            echte(self, tenant_id, bid, meta)

        monkeypatch.setattr(BonBevestiging, "_markeer_afgerond", _na_opruiming)

        o.bevestiging.bevestig(1, bestand_id, dict(GOED), gebruiker_id=7)

        assert not (o.root / "1" / f"{bestand_id}.meta.json").exists()
