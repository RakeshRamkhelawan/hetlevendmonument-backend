"""Acceptatie dag 4, blokkade 1: het leesresultaat verdween na ~6 minuten, terwijl de tekst 30 dagen belooft.

Gemeten op de acceptatie-opstelling (2026-10-17): de resultaatsleutel in de bonlezer-Redis had 286 s van 300 s
over (`RESULTAAT_TTL_MS`), daarna "Het leesresultaat is niet meer beschikbaar". Nu: de bewaartijd in Redis is
30 dagen, en de backend legt het resultaat bij de eerste keer ophalen ook naast de bon vast
(`<bestand_id>.resultaat.json`, geen tabel), zodat een herstart van Redis het niet kwijtmaakt. De opruiming
verwijdert dat bestand met de bon na 30 dagen (zie `test_opruimen.py`).

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from dramatiq.results import ResultMissing

from src.core.als.bonlezer import worker as worker_module
from src.core.als.bonlezer.upload import VERLOOP_SECONDEN, BonDienst, BonNietGevonden

PDF = b"%PDF-1.4\n% een proefbestand\n"
START = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)
DAG_MS = 24 * 60 * 60 * 1000
VELDEN = {
    "leverancier": "Bakkerij De Korenaar B.V.",
    "datum": "2026-10-01",
    "totaal": "12.10",
    "factuurnummer": "F-2026-001",
    "btw": {"9": "0.50", "21": "1.60"},
    "btw_nummer": "NL123456789B01",
    "kvk_nummer": "12345678",
}


class _Werkplaats:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.resultaten: dict[str, dict[str, object]] = {}
        self.nu = START
        self.dienst = BonDienst(root, verstuur=self._verstuur, haal=self._haal, nu=lambda: self.nu)
        self.teller = 0

    def _verstuur(self, tenant_id: int, bestand_id: str) -> str:
        self.teller += 1
        return f"bericht-{self.teller}"

    def _haal(self, message_id: str) -> dict[str, object]:
        if message_id not in self.resultaten:
            raise ResultMissing(message_id)  # type: ignore[call-arg]
        return self.resultaten[message_id]

    def bon_met_resultaat(self, tenant: int = 1, status: str = "gelezen") -> str:
        bestand_id = self.dienst.uploaden(tenant, "a.pdf", PDF)
        self.resultaten[f"bericht-{self.teller}"] = {
            "status": status,
            "reden": "" if status == "gelezen" else "kon niet",
            "sha256": hashlib.sha256(PDF).hexdigest(),
            "velden": dict(VELDEN),
        }
        return bestand_id

    def verlies_het_resultaat_in_redis(self) -> None:
        self.resultaten.clear()


@pytest.fixture
def w(tmp_path: Path) -> _Werkplaats:
    return _Werkplaats(tmp_path)


class TestDeBewaartijdInRedis:
    def test_the_result_time_in_redis_is_at_least_30_days(self) -> None:
        assert worker_module.RESULTAAT_TTL_MS >= 30 * DAG_MS

    def test_the_time_without_any_result_stays_short(self) -> None:
        """Een opdracht die nooit een resultaat krijgt (worker weg) hoort niet 30 dagen "wachten" te blijven."""
        assert VERLOOP_SECONDEN <= 600


class TestHetResultaatBlijftBeschikbaar:
    def test_the_result_is_still_there_after_redis_lost_it(self, w: _Werkplaats) -> None:
        bestand_id = w.bon_met_resultaat()
        w.dienst.status(1, bestand_id)
        w.verlies_het_resultaat_in_redis()

        assert w.dienst.status(1, bestand_id)["status"] == "gelezen"

    def test_the_fields_are_still_there_after_redis_lost_it(self, w: _Werkplaats) -> None:
        bestand_id = w.bon_met_resultaat()
        w.dienst.status(1, bestand_id)
        w.verlies_het_resultaat_in_redis()

        antwoord = w.dienst.status(1, bestand_id)

        assert antwoord["velden"] == VELDEN

    def test_the_result_is_still_there_29_days_later(self, w: _Werkplaats) -> None:
        bestand_id = w.bon_met_resultaat()
        w.dienst.status(1, bestand_id)
        w.verlies_het_resultaat_in_redis()
        w.nu = START + timedelta(days=29)

        assert w.dienst.status(1, bestand_id)["status"] == "gelezen"

    def test_the_result_is_stored_next_to_the_bon(self, w: _Werkplaats) -> None:
        bestand_id = w.bon_met_resultaat()

        w.dienst.status(1, bestand_id)

        assert (w.root / "1" / f"{bestand_id}.resultaat.json").is_file()

    def test_a_refused_bon_keeps_its_reason_too(self, w: _Werkplaats) -> None:
        bestand_id = w.bon_met_resultaat(status="geweigerd")
        w.dienst.status(1, bestand_id)
        w.verlies_het_resultaat_in_redis()

        antwoord = w.dienst.status(1, bestand_id)

        assert (antwoord["status"], antwoord["reden"]) == ("geweigerd", "kon niet")

    def test_a_bon_that_is_still_waiting_stores_no_result(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)

        w.dienst.status(1, bestand_id)

        assert not (w.root / "1" / f"{bestand_id}.resultaat.json").exists()

    def test_a_result_for_another_file_is_not_stored(self, w: _Werkplaats) -> None:
        bestand_id = w.bon_met_resultaat()
        w.resultaten["bericht-1"]["sha256"] = "0" * 64

        antwoord = w.dienst.status(1, bestand_id)

        assert antwoord["status"] == "ongeldig"
        assert not (w.root / "1" / f"{bestand_id}.resultaat.json").exists()

    def test_a_stored_result_with_fields_outside_the_schema_is_not_shown(
        self, w: _Werkplaats
    ) -> None:
        bestand_id = w.bon_met_resultaat()
        w.dienst.status(1, bestand_id)
        w.verlies_het_resultaat_in_redis()
        pad = w.root / "1" / f"{bestand_id}.resultaat.json"
        record = json.loads(pad.read_text(encoding="utf-8"))
        record["velden"]["onbekend"] = "x"
        pad.write_text(json.dumps(record), encoding="utf-8")

        assert w.dienst.status(1, bestand_id)["status"] == "ongeldig"

    def test_a_damaged_stored_result_gives_expired_and_not_a_crash(self, w: _Werkplaats) -> None:
        bestand_id = w.bon_met_resultaat()
        w.dienst.status(1, bestand_id)
        w.verlies_het_resultaat_in_redis()
        (w.root / "1" / f"{bestand_id}.resultaat.json").write_text("{kapot", encoding="utf-8")

        assert w.dienst.status(1, bestand_id)["status"] == "verlopen"

    def test_a_damaged_stored_result_falls_back_on_redis_while_redis_still_has_it(
        self, w: _Werkplaats
    ) -> None:
        """Security-review: een kapot bestand mocht de bon niet 30 dagen onleesbaar maken."""
        bestand_id = w.bon_met_resultaat()
        w.dienst.status(1, bestand_id)
        (w.root / "1" / f"{bestand_id}.resultaat.json").write_text("{kapot", encoding="utf-8")

        assert w.dienst.status(1, bestand_id)["status"] == "gelezen"

    def test_a_damaged_stored_result_is_rewritten_from_redis(self, w: _Werkplaats) -> None:
        bestand_id = w.bon_met_resultaat()
        w.dienst.status(1, bestand_id)
        pad = w.root / "1" / f"{bestand_id}.resultaat.json"
        pad.write_text("{kapot", encoding="utf-8")
        w.dienst.status(1, bestand_id)
        w.verlies_het_resultaat_in_redis()

        assert w.dienst.status(1, bestand_id)["status"] == "gelezen"

    def test_a_deeply_nested_stored_result_is_no_crash(self, w: _Werkplaats) -> None:
        """Security-review ronde 2: `RecursionError` in het lezen gaf een 500 op de statusvraag."""
        bestand_id = w.bon_met_resultaat()
        w.dienst.status(1, bestand_id)
        (w.root / "1" / f"{bestand_id}.resultaat.json").write_text("[" * 20000, encoding="utf-8")

        assert w.dienst.status(1, bestand_id)["status"] == "gelezen"

    def test_another_tenant_does_not_see_the_stored_result(self, w: _Werkplaats) -> None:
        bestand_id = w.bon_met_resultaat(tenant=1)
        w.dienst.status(1, bestand_id)

        with pytest.raises(BonNietGevonden):
            w.dienst.status(2, bestand_id)

    def test_the_stored_result_is_not_overwritten_by_a_later_one(self, w: _Werkplaats) -> None:
        bestand_id = w.bon_met_resultaat()
        w.dienst.status(1, bestand_id)
        w.resultaten["bericht-1"]["velden"] = {**VELDEN, "totaal": "99.99"}  # type: ignore[dict-item]

        assert w.dienst.status(1, bestand_id)["velden"]["totaal"] == "12.10"  # type: ignore[index]
