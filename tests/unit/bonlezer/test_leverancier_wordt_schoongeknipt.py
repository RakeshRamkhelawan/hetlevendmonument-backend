"""Ruis voor of achter de leverancier wordt weggeknipt (zero-admin afwerken, 2026-10-19).

Acceptatie: de bonlezer leest soms "_Bakkerij De Korenaar B.V._" of "- Jumbo -" als leverancier; dat stond zo op het
scherm, in de lijst en in de bevestigde velden. Nu knipt `_maak_schoon` aan beide kanten tekens als `_ - | * ~ # / \\`
weg (en een komma, puntkomma of dubbele punt achteraan, en een punt vooraan); een punt ACHTERAAN blijft staan omdat
"B.V." eindigt op een punt. Alleen de leverancier: andere velden blijven zoals ze zijn.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.core.als.bonlezer.bevestiging import BonBevestiging
from src.core.als.bonlezer.upload import BonDienst, UploadFout

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


@pytest.fixture
def bevestiging(tmp_path: Path) -> BonBevestiging:
    return BonBevestiging(tmp_path, nu=lambda: START)


def _gelezen(velden: dict[str, object]) -> dict[str, object]:
    return {"status": "gelezen", "velden": velden}


class TestHetScherm:
    @pytest.mark.parametrize(
        ("gelezen", "verwacht"),
        [
            ("_Bakkerij De Korenaar B.V._", "Bakkerij De Korenaar B.V."),
            ("__Albert Heijn__", "Albert Heijn"),
            ("- Jumbo -", "Jumbo"),
            ("|Shell|", "Shell"),
            ("*Action*", "Action"),
            ("~Kruidvat~", "Kruidvat"),
            ("#Hema#", "Hema"),
            ("/Gamma/", "Gamma"),
            ("\\Praxis\\", "Praxis"),
            ("Bakkerij Jansen,", "Bakkerij Jansen"),
            ("Bakkerij Jansen;", "Bakkerij Jansen"),
            ("Bakkerij Jansen:", "Bakkerij Jansen"),
            (".Slagerij Pietersen", "Slagerij Pietersen"),
            ("_ - _Bouwmarkt_ - _", "Bouwmarkt"),
            ("  _Bakker_  ", "Bakker"),
        ],
    )
    def test_noise_around_the_vendor_is_cut_off(
        self, bevestiging: BonBevestiging, gelezen: str, verwacht: str
    ) -> None:
        uit = bevestiging.verrijk(1, "x" * 32 + ".pdf", _gelezen({**GOED, "leverancier": gelezen}))

        assert uit["velden"]["leverancier"] == verwacht  # type: ignore[index]

    @pytest.mark.parametrize(
        "ongemoeid",
        [
            "Bakkerij De Korenaar B.V.",
            "A_B Beheer",
            "Jumbo Supermarkten B.V.",
            "Albert-Heijn Zaandam",
            "Maatschap A/B",
            "Cafe 't Hoekje",
            "(Kantoor) Gemeente Utrecht",
            "100% Bakker",
        ],
    )
    def test_a_normal_name_is_not_changed(
        self, bevestiging: BonBevestiging, ongemoeid: str
    ) -> None:
        uit = bevestiging.verrijk(
            1, "x" * 32 + ".pdf", _gelezen({**GOED, "leverancier": ongemoeid})
        )

        assert uit["velden"]["leverancier"] == ongemoeid  # type: ignore[index]

    def test_a_vendor_of_only_noise_becomes_empty(self, bevestiging: BonBevestiging) -> None:
        uit = bevestiging.verrijk(1, "x" * 32 + ".pdf", _gelezen({**GOED, "leverancier": "___"}))

        assert uit["velden"]["leverancier"] == ""  # type: ignore[index]

    def test_an_empty_vendor_is_to_be_checked(self, bevestiging: BonBevestiging) -> None:
        uit = bevestiging.verrijk(1, "x" * 32 + ".pdf", _gelezen({**GOED, "leverancier": "___"}))

        assert uit["controleren"]["leverancier"] == "controleren"  # type: ignore[index]

    def test_other_fields_keep_their_noise(self, bevestiging: BonBevestiging) -> None:
        uit = bevestiging.verrijk(
            1, "x" * 32 + ".pdf", _gelezen({**GOED, "factuurnummer": "_F-2026-001_"})
        )

        assert uit["velden"]["factuurnummer"] == "_F-2026-001_"  # type: ignore[index]

    def test_a_missing_vendor_stays_missing(self, bevestiging: BonBevestiging) -> None:
        velden = {k: v for k, v in GOED.items() if k != "leverancier"}

        uit = bevestiging.verrijk(1, "x" * 32 + ".pdf", _gelezen(velden))

        assert "leverancier" not in uit["velden"]  # type: ignore[operator]

    def test_a_vendor_that_is_not_text_is_left_alone(self, bevestiging: BonBevestiging) -> None:
        uit = bevestiging.verrijk(1, "x" * 32 + ".pdf", _gelezen({**GOED, "leverancier": None}))

        assert uit["velden"]["leverancier"] is None  # type: ignore[index]


class TestBevestigen:
    def _dienst(self, root: Path) -> BonDienst:
        return BonDienst(root, verstuur=lambda t, b: "bericht", haal=lambda m: {}, nu=lambda: START)

    def test_the_confirmed_vendor_is_trimmed(self, tmp_path: Path) -> None:
        dienst = self._dienst(tmp_path)
        bevestiging = BonBevestiging(tmp_path, nu=lambda: START)
        bestand_id = dienst.uploaden(1, "a.pdf", PDF)

        bevestiging.bevestig(1, bestand_id, {**GOED, "leverancier": "_Jumbo_"}, gebruiker_id=1)

        record = bevestiging.bevestigd(1, bestand_id) or {}
        assert record["velden"]["leverancier"] == "Jumbo"  # type: ignore[index]

    def test_a_vendor_of_only_noise_cannot_be_confirmed(self, tmp_path: Path) -> None:
        dienst = self._dienst(tmp_path)
        bevestiging = BonBevestiging(tmp_path, nu=lambda: START)
        bestand_id = dienst.uploaden(1, "a.pdf", PDF)

        with pytest.raises(UploadFout) as fout:
            bevestiging.bevestig(1, bestand_id, {**GOED, "leverancier": "___"}, gebruiker_id=1)

        assert fout.value.error_code == "VELDEN_CONTROLEREN"

    def test_the_vendor_in_the_csv_is_trimmed(self, tmp_path: Path) -> None:
        dienst = self._dienst(tmp_path)
        bevestiging = BonBevestiging(tmp_path, nu=lambda: START)
        bestand_id = dienst.uploaden(1, "a.pdf", PDF)
        bevestiging.bevestig(1, bestand_id, {**GOED, "leverancier": "- Jumbo -"}, gebruiker_id=1)

        rijen = bevestiging.csv_export(1)

        assert ",Jumbo," in rijen and "- Jumbo" not in rijen
