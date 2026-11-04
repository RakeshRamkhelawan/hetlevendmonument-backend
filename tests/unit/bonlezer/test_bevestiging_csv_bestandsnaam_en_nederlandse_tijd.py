"""De CSV van bevestigde bonnen heeft de bestandsnaam en Nederlandse tijd (zero-admin afwerken, 2026-10-19).

Acceptatie (2026-10-18): de CSV had `bestand_id` (een hexcode waar niemand iets mee kan) in plaats van de naam van het
bestand dat de medewerker uploadde, en `bevestigd_op` in UTC. Nu bewaart de bevestiging de (door de server
schoongemaakte) bestandsnaam en toont de CSV `bestandsnaam` en de tijd in Europe/Amsterdam met tijdzone
(`2026-10-17 11:00:00+02:00`). De naam komt van de gebruiker: in de CSV is hij net zo veilig als elke andere tekst
(stuurtekens eruit, een apostrof voor een cel die als formule gelezen kan worden).

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.core.als.bonlezer.bevestiging import BonBevestiging
from src.core.als.bonlezer.upload import BonDienst

PDF = b"%PDF-1.4\n% een proefbestand\n"
ZOMER = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)
WINTER = datetime(2026, 12, 17, 9, 0, tzinfo=timezone.utc)

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
    def __init__(self, root: Path, nu: datetime) -> None:
        self.root = root
        self.dienst = BonDienst(
            root, verstuur=lambda t, b: "bericht", haal=lambda m: {}, nu=lambda: nu
        )
        self.bevestiging = BonBevestiging(root, nu=lambda: nu)

    def bevestigde_bon(self, naam: str = "factuur-oktober.pdf") -> str:
        bestand_id = self.dienst.uploaden(1, naam, PDF)
        self.bevestiging.bevestig(1, bestand_id, dict(GOED), gebruiker_id=1)
        return bestand_id

    def rijen(self) -> list[dict[str, str]]:
        return list(csv.DictReader(io.StringIO(self.bevestiging.csv_export(1))))


@pytest.fixture
def zomer(tmp_path: Path) -> _Opstelling:
    return _Opstelling(tmp_path, ZOMER)


class TestDeBestandsnaamInDeCsv:
    def test_the_file_name_is_the_first_column_and_the_id_stays_as_the_last(
        self, zomer: _Opstelling
    ) -> None:
        kop = zomer.bevestiging.csv_export(1).splitlines()[0].split(",")

        assert (kop[0], kop[-1]) == ("bestandsnaam", "bestand_id")

    def test_the_id_identifies_the_row_even_without_a_name(self, zomer: _Opstelling) -> None:
        bestand_id = zomer.bevestigde_bon()
        pad = zomer.root / "1" / f"{bestand_id}.bevestigd.json"
        record = json.loads(pad.read_text(encoding="utf-8"))
        del record["naam"]
        pad.write_text(json.dumps(record), encoding="utf-8")

        rij = zomer.rijen()[0]

        assert (rij["bestandsnaam"], rij["bestand_id"]) == ("", bestand_id)

    def test_two_bonnen_with_the_same_name_have_different_ids(self, zomer: _Opstelling) -> None:
        een = zomer.bevestigde_bon("factuur.pdf")
        twee = zomer.dienst.uploaden(1, "factuur.pdf", PDF + b"x")
        zomer.bevestiging.bevestig(1, twee, dict(GOED), gebruiker_id=1)

        ids = {rij["bestand_id"] for rij in zomer.rijen()}

        assert ids == {een, twee}

    def test_the_row_has_the_original_file_name(self, zomer: _Opstelling) -> None:
        zomer.bevestigde_bon("factuur-oktober.pdf")

        assert zomer.rijen()[0]["bestandsnaam"] == "factuur-oktober.pdf"

    def test_a_path_in_the_name_is_not_in_the_csv(self, zomer: _Opstelling) -> None:
        zomer.bevestigde_bon("C:\\Users\\Jan\\Documenten\\factuur.pdf")

        assert zomer.rijen()[0]["bestandsnaam"] == "factuur.pdf"

    def test_a_formula_name_gets_an_apostrophe(self, zomer: _Opstelling) -> None:
        zomer.bevestigde_bon("=HYPERLINK(1).pdf")

        assert zomer.rijen()[0]["bestandsnaam"].startswith("'=")

    def test_the_name_is_stored_in_the_confirmation_not_read_from_the_bon_later(
        self, zomer: _Opstelling
    ) -> None:
        bestand_id = zomer.bevestigde_bon("factuur-oktober.pdf")
        (zomer.root / "1" / f"{bestand_id}.meta.json").unlink()

        assert zomer.rijen()[0]["bestandsnaam"] == "factuur-oktober.pdf"

    def test_an_old_confirmation_without_a_name_has_an_empty_cell(self, zomer: _Opstelling) -> None:
        bestand_id = zomer.bevestigde_bon()
        pad = zomer.root / "1" / f"{bestand_id}.bevestigd.json"
        record = json.loads(pad.read_text(encoding="utf-8"))
        del record["naam"]
        pad.write_text(json.dumps(record), encoding="utf-8")

        assert zomer.rijen()[0]["bestandsnaam"] == ""

    def test_the_name_is_in_the_confirmation_record(self, zomer: _Opstelling) -> None:
        bestand_id = zomer.bevestigde_bon("factuur-oktober.pdf")

        record = zomer.bevestiging.bevestigd(1, bestand_id)

        assert (record or {}).get("naam") == "factuur-oktober.pdf"


class TestDeTijdInDeCsv:
    def test_summer_time_has_plus_two(self, zomer: _Opstelling) -> None:
        zomer.bevestigde_bon()

        assert zomer.rijen()[0]["bevestigd_op"] == "2026-10-17 11:00:00+02:00"

    def test_winter_time_has_plus_one(self, tmp_path: Path) -> None:
        winter = _Opstelling(tmp_path, WINTER)
        winter.bevestigde_bon()

        assert winter.rijen()[0]["bevestigd_op"] == "2026-12-17 10:00:00+01:00"

    def test_an_unreadable_time_is_an_empty_cell_and_not_a_crash(self, zomer: _Opstelling) -> None:
        bestand_id = zomer.bevestigde_bon()
        pad = zomer.root / "1" / f"{bestand_id}.bevestigd.json"
        record = json.loads(pad.read_text(encoding="utf-8"))
        record["bevestigd_op"] = "gisteren"
        pad.write_text(json.dumps(record), encoding="utf-8")

        assert zomer.rijen()[0]["bevestigd_op"] == ""

    def test_a_time_without_a_zone_is_taken_as_utc(self, zomer: _Opstelling) -> None:
        bestand_id = zomer.bevestigde_bon()
        pad = zomer.root / "1" / f"{bestand_id}.bevestigd.json"
        record = json.loads(pad.read_text(encoding="utf-8"))
        record["bevestigd_op"] = "2026-10-17T09:00:00"
        pad.write_text(json.dumps(record), encoding="utf-8")

        assert zomer.rijen()[0]["bevestigd_op"] == "2026-10-17 11:00:00+02:00"
