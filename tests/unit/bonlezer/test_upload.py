"""De opslag- en statuskant van de bonlezer in de backend (bonlezer dag 3).

Brief `docs/agent-briefs/generated/2026-10-17-sprint-dag-bonlezer-dag3-eigen-redis-en-upload.md`.
`BonDienst` bewaart een upload onder `<uploadmap>/<tenant_id>/<bestand_id>`, stuurt de opdracht naar de
worker en toetst het resultaat aan wat de backend zelf bij de upload heeft vastgelegd. Er is geen tabel:
de gegevens per upload (sha256, bericht-id, tijdstip) staan in een bestand naast de bon, op het volume dat
de worker alleen mag lezen. De verzending en het ophalen van het resultaat zijn hier nagemaakt; de echte
worker en broker komen aan bod in `tests/integration/test_bonlezer_upload.py`.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import errno
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from dramatiq.results import ResultMissing

from src.core.als.bonlezer import upload as upload_module
from src.core.als.bonlezer.upload import (
    MAX_OPENSTAAND,
    OPENSTAAND_SECONDEN,
    VERLOOP_SECONDEN,
    BonDienst,
    BonNietGevonden,
    UploadFout,
)

PDF = b"%PDF-1.4\n% een proefbestand\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 20
JPG = b"\xff\xd8\xff\xe0" + b"x" * 20
START = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)


class _Werkplaats:
    """Een dienst met een nagemaakte verzending en een nagemaakte resultaatopslag."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.verstuurd: list[tuple[int, str]] = []
        self.resultaten: dict[str, dict[str, object]] = {}
        self.nu = START
        self.verstuur_fout: Exception | None = None
        self.dienst = BonDienst(root, verstuur=self._verstuur, haal=self._haal, nu=lambda: self.nu)

    def _verstuur(self, tenant_id: int, bestand_id: str) -> str:
        if self.verstuur_fout is not None:
            raise self.verstuur_fout
        self.verstuurd.append((tenant_id, bestand_id))
        return f"bericht-{len(self.verstuurd)}"

    def _haal(self, message_id: str) -> dict[str, object]:
        if message_id not in self.resultaten:
            raise ResultMissing(message_id)  # type: ignore[call-arg]
        return self.resultaten[message_id]

    def bestanden(self) -> list[str]:
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file())


@pytest.fixture
def w(tmp_path: Path) -> _Werkplaats:
    return _Werkplaats(tmp_path)


class TestHetBestandWordtPasOpgeslagenAlsHetKlopt:
    def test_a_file_that_is_too_large_leaves_nothing_on_disk(
        self, w: _Werkplaats, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(upload_module, "MAX_BYTES", 10)

        with pytest.raises(UploadFout):
            w.dienst.uploaden(1, "bon.pdf", PDF)

        assert w.bestanden() == []

    def test_a_file_that_is_too_large_is_refused_with_413(
        self, w: _Werkplaats, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(upload_module, "MAX_BYTES", 10)

        with pytest.raises(UploadFout) as fout:
            w.dienst.uploaden(1, "bon.pdf", PDF)

        assert fout.value.status_code == 413

    @pytest.mark.parametrize("naam", ["bon.exe", "bon", "bon.pdf.exe", "bon.html", "../bon.zip"])
    def test_a_file_of_another_type_leaves_nothing_on_disk(self, w: _Werkplaats, naam: str) -> None:
        with pytest.raises(UploadFout):
            w.dienst.uploaden(1, naam, PDF)

        assert w.bestanden() == []

    def test_a_file_whose_content_does_not_match_its_extension_leaves_nothing_on_disk(
        self, w: _Werkplaats
    ) -> None:
        with pytest.raises(UploadFout):
            w.dienst.uploaden(1, "bon.pdf", PNG)

        assert w.bestanden() == []

    def test_a_file_of_the_wrong_type_is_refused_with_415(self, w: _Werkplaats) -> None:
        with pytest.raises(UploadFout) as fout:
            w.dienst.uploaden(1, "bon.exe", PDF)

        assert fout.value.status_code == 415

    def test_an_empty_file_is_refused(self, w: _Werkplaats) -> None:
        with pytest.raises(UploadFout):
            w.dienst.uploaden(1, "bon.pdf", b"")

        assert w.bestanden() == []

    def test_an_empty_file_is_refused_as_empty_and_not_as_a_wrong_type(
        self, w: _Werkplaats
    ) -> None:
        with pytest.raises(UploadFout) as fout:
            w.dienst.uploaden(1, "bon.pdf", b"")

        assert (fout.value.status_code, fout.value.error_code) == (422, "FILE_EMPTY")

    def test_nothing_is_sent_to_the_worker_for_a_refused_file(self, w: _Werkplaats) -> None:
        with pytest.raises(UploadFout):
            w.dienst.uploaden(1, "bon.exe", PDF)

        assert w.verstuurd == []

    @pytest.mark.parametrize(
        ("naam", "inhoud"),
        [
            ("a.pdf", PDF),
            ("a.png", PNG),
            ("a.jpg", JPG),
            ("a.JPEG", JPG),
            ("a.tif", b"II*\x00xxxx"),
        ],
    )
    def test_the_accepted_types_are_stored(self, w: _Werkplaats, naam: str, inhoud: bytes) -> None:
        bestand_id = w.dienst.uploaden(1, naam, inhoud)

        assert (w.root / "1" / bestand_id).read_bytes() == inhoud


class TestHetBestandId:
    def test_the_id_is_32_random_hex_characters_and_an_extension(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(1, "mijn bon.PDF", PDF)

        assert re.fullmatch(r"[0-9a-f]{32}\.pdf", bestand_id) is not None

    def test_the_id_is_not_derived_from_the_content(self, w: _Werkplaats) -> None:
        eerste = w.dienst.uploaden(1, "a.pdf", PDF)
        tweede = w.dienst.uploaden(1, "a.pdf", PDF)

        assert eerste.split(".")[0] != tweede.split(".")[0]

    def test_the_id_does_not_contain_the_name_of_the_user(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(1, "geheim-salaris.pdf", PDF)

        assert "geheim" not in bestand_id

    def test_the_id_comes_from_the_token_generator(
        self, w: _Werkplaats, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(upload_module.secrets, "token_hex", lambda n: "ab" * n)

        assert w.dienst.uploaden(1, "a.pdf", PDF) == "ab" * 16 + ".pdf"


class TestDeOpslagPerTenant:
    def test_the_file_is_stored_in_the_folder_of_the_tenant(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(7, "a.pdf", PDF)

        assert (w.root / "7" / bestand_id).read_bytes() == PDF

    def test_the_order_for_the_worker_carries_the_tenant_and_the_id(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(7, "a.pdf", PDF)

        assert w.verstuurd == [(7, bestand_id)]

    def test_the_hash_of_the_upload_is_kept_next_to_the_file(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(7, "a.pdf", PDF)

        meta = json.loads((w.root / "7" / f"{bestand_id}.meta.json").read_text(encoding="utf-8"))
        assert meta["sha256"] == hashlib.sha256(PDF).hexdigest()

    def test_the_message_id_is_kept_next_to_the_file(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(7, "a.pdf", PDF)

        meta = json.loads((w.root / "7" / f"{bestand_id}.meta.json").read_text(encoding="utf-8"))
        assert meta["message_id"] == "bericht-1"

    def test_the_original_name_is_not_kept_anywhere(self, w: _Werkplaats) -> None:
        w.dienst.uploaden(7, "geheim-salaris.pdf", PDF)

        assert all("geheim" not in p for p in w.bestanden())

    def test_when_the_order_cannot_be_sent_nothing_stays_behind(self, w: _Werkplaats) -> None:
        w.verstuur_fout = ConnectionError("redis weg")

        with pytest.raises(UploadFout):
            w.dienst.uploaden(7, "a.pdf", PDF)

        assert w.bestanden() == []

    def test_when_the_order_cannot_be_sent_the_answer_is_503(self, w: _Werkplaats) -> None:
        w.verstuur_fout = ConnectionError("redis weg")

        with pytest.raises(UploadFout) as fout:
            w.dienst.uploaden(7, "a.pdf", PDF)

        assert fout.value.status_code == 503

    def test_a_tenant_id_that_is_not_a_positive_whole_number_is_refused(
        self, w: _Werkplaats
    ) -> None:
        with pytest.raises(UploadFout):
            w.dienst.uploaden(0, "a.pdf", PDF)

        assert w.bestanden() == []


class TestDeStatus:
    def test_another_tenant_does_not_find_the_upload(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)

        with pytest.raises(BonNietGevonden):
            w.dienst.status(2, bestand_id)

    def test_an_unknown_id_is_not_found(self, w: _Werkplaats) -> None:
        with pytest.raises(BonNietGevonden):
            w.dienst.status(1, "0" * 32 + ".pdf")

    @pytest.mark.parametrize(
        "bestand_id", ["../2/x.pdf", "x", "", "0" * 32, "0" * 32 + ".exe", "A" * 32 + ".pdf"]
    )
    def test_an_id_of_another_shape_is_not_found(self, w: _Werkplaats, bestand_id: str) -> None:
        with pytest.raises(BonNietGevonden):
            w.dienst.status(1, bestand_id)

    def test_an_id_with_a_path_to_the_folder_of_another_tenant_is_not_found(
        self, w: _Werkplaats
    ) -> None:
        """Pad-ontsnapping: `../2/<id>` moet niet bij de bon van tenant 2 uitkomen."""
        bestand_id = w.dienst.uploaden(2, "a.pdf", PDF)

        with pytest.raises(BonNietGevonden):
            w.dienst.status(1, f"../2/{bestand_id}")

    def test_a_negative_or_zero_tenant_does_not_find_anything(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)

        with pytest.raises(BonNietGevonden):
            w.dienst.status(0, bestand_id)

    def test_without_a_result_the_status_is_waiting(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)

        assert w.dienst.status(1, bestand_id)["status"] == "wachten"

    def test_a_result_with_the_hash_of_the_upload_is_shown(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)
        w.resultaten["bericht-1"] = {
            "status": "gelezen",
            "reden": "",
            "sha256": hashlib.sha256(PDF).hexdigest(),
            "velden": {"totaal": "12.10"},
        }

        antwoord = w.dienst.status(1, bestand_id)

        assert (antwoord["status"], antwoord["velden"]) == ("gelezen", {"totaal": "12.10"})

    def test_a_result_with_another_hash_is_not_shown(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)
        w.resultaten["bericht-1"] = {
            "status": "gelezen",
            "reden": "",
            "sha256": hashlib.sha256(b"iets anders").hexdigest(),
            "velden": {"totaal": "999.00"},
        }

        antwoord = w.dienst.status(1, bestand_id)

        assert (antwoord["status"], antwoord.get("velden")) == ("ongeldig", None)

    def test_a_result_without_a_hash_that_claims_to_be_read_is_not_shown(
        self, w: _Werkplaats
    ) -> None:
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)
        w.resultaten["bericht-1"] = {"status": "gelezen", "reden": "", "velden": {"totaal": "1.00"}}

        assert w.dienst.status(1, bestand_id)["status"] == "ongeldig"

    def test_a_refusal_of_the_worker_is_passed_on_with_its_reason(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)
        w.resultaten["bericht-1"] = {
            "status": "geweigerd",
            "reden": "de inhoud past niet bij de extensie",
            "sha256": "",
            "velden": {},
        }

        antwoord = w.dienst.status(1, bestand_id)

        assert (antwoord["status"], antwoord["reden"]) == (
            "geweigerd",
            "de inhoud past niet bij de extensie",
        )

    def test_an_error_of_the_worker_is_passed_on_without_fields(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)
        w.resultaten["bericht-1"] = {
            "status": "fout",
            "reden": "RuntimeError",
            "sha256": "",
            "velden": {},
        }

        assert w.dienst.status(1, bestand_id)["status"] == "fout"

    def test_a_result_that_is_not_a_known_status_is_not_shown(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)
        w.resultaten["bericht-1"] = {"status": "ok", "velden": {"totaal": "1.00"}}

        assert w.dienst.status(1, bestand_id)["status"] == "ongeldig"

    def test_a_result_that_is_not_a_dict_is_not_shown(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)
        w.resultaten["bericht-1"] = "gelezen"  # type: ignore[assignment]

        assert w.dienst.status(1, bestand_id)["status"] == "ongeldig"

    def test_after_the_result_has_expired_the_status_is_expired(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)
        w.nu = START + timedelta(seconds=OPENSTAAND_SECONDEN + 1)

        assert w.dienst.status(1, bestand_id)["status"] == "verlopen"

    def test_when_the_result_store_is_down_the_answer_is_503(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)

        def stuk(message_id: str) -> dict[str, object]:
            raise ConnectionError("redis weg")

        w.dienst = BonDienst(w.root, verstuur=w._verstuur, haal=stuk, nu=lambda: w.nu)

        with pytest.raises(UploadFout) as fout:
            w.dienst.status(1, bestand_id)

        assert fout.value.status_code == 503

    def test_the_answer_never_contains_the_hash_of_the_worker_or_a_path(
        self, w: _Werkplaats
    ) -> None:
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)
        w.resultaten["bericht-1"] = {
            "status": "gelezen",
            "reden": "",
            "sha256": hashlib.sha256(PDF).hexdigest(),
            "velden": {},
        }

        tekst = json.dumps(w.dienst.status(1, bestand_id))

        assert hashlib.sha256(PDF).hexdigest() not in tekst and str(w.root) not in tekst


class TestHetQuotum:
    def test_up_to_the_quota_every_upload_is_accepted(self, w: _Werkplaats) -> None:
        for _ in range(MAX_OPENSTAAND):
            w.dienst.uploaden(1, "a.pdf", PDF)

        assert len(w.verstuurd) == MAX_OPENSTAAND

    def test_above_the_quota_the_answer_is_429(self, w: _Werkplaats) -> None:
        for _ in range(MAX_OPENSTAAND):
            w.dienst.uploaden(1, "a.pdf", PDF)

        with pytest.raises(UploadFout) as fout:
            w.dienst.uploaden(1, "a.pdf", PDF)

        assert fout.value.status_code == 429

    def test_the_message_over_the_quota_is_in_dutch(self, w: _Werkplaats) -> None:
        for _ in range(MAX_OPENSTAAND):
            w.dienst.uploaden(1, "a.pdf", PDF)

        with pytest.raises(UploadFout) as fout:
            w.dienst.uploaden(1, "a.pdf", PDF)

        assert "wachten" in fout.value.boodschap and "opnieuw" in fout.value.boodschap

    def test_above_the_quota_nothing_is_stored_or_sent(self, w: _Werkplaats) -> None:
        for _ in range(MAX_OPENSTAAND):
            w.dienst.uploaden(1, "a.pdf", PDF)
        voor = (w.bestanden(), list(w.verstuurd))

        with pytest.raises(UploadFout):
            w.dienst.uploaden(1, "a.pdf", PDF)

        assert (w.bestanden(), w.verstuurd) == voor

    def test_the_quota_is_per_tenant(self, w: _Werkplaats) -> None:
        for _ in range(MAX_OPENSTAAND):
            w.dienst.uploaden(1, "a.pdf", PDF)

        w.dienst.uploaden(2, "a.pdf", PDF)

        assert w.verstuurd[-1][0] == 2

    def test_a_finished_order_no_longer_counts(self, w: _Werkplaats) -> None:
        eerste = w.dienst.uploaden(1, "a.pdf", PDF)
        for _ in range(MAX_OPENSTAAND - 1):
            w.dienst.uploaden(1, "a.pdf", PDF)
        w.resultaten["bericht-1"] = {
            "status": "gelezen",
            "reden": "",
            "sha256": hashlib.sha256(PDF).hexdigest(),
            "velden": {},
        }
        w.dienst.status(1, eerste)

        w.dienst.uploaden(1, "a.pdf", PDF)

        assert len(w.verstuurd) == MAX_OPENSTAAND + 1

    def test_an_old_order_no_longer_counts(self, w: _Werkplaats) -> None:
        for _ in range(MAX_OPENSTAAND):
            w.dienst.uploaden(1, "a.pdf", PDF)
        w.nu = START + timedelta(seconds=OPENSTAAND_SECONDEN + 1)

        w.dienst.uploaden(1, "a.pdf", PDF)

        assert len(w.verstuurd) == MAX_OPENSTAAND + 1

    def test_a_refused_file_does_not_count_towards_the_quota(self, w: _Werkplaats) -> None:
        for _ in range(MAX_OPENSTAAND + 3):
            with pytest.raises(UploadFout):
                w.dienst.uploaden(1, "a.exe", PDF)

        w.dienst.uploaden(1, "a.pdf", PDF)

        assert len(w.verstuurd) == 1

    def test_uploads_that_overlap_cannot_all_pass_the_quota(self, w: _Werkplaats) -> None:
        """Security-review ronde 1: de reservering moet er staan VOOR de verzending.

        Tijdens het versturen van elke opdracht komt er een gelijktijdige upload binnen (een
        geneste aanroep). Staat het metabestand pas na het versturen, dan ziet elke upload nul
        openstaande opdrachten en komt er nooit een 429.
        """
        uitkomsten: list[int] = []

        def verstuur(tenant_id: int, bestand_id: str) -> str:
            if len(uitkomsten) < MAX_OPENSTAAND + 3:
                uitkomsten.append(0)
                positie = len(uitkomsten) - 1
                try:
                    dienst.uploaden(tenant_id, "a.pdf", PDF)
                    uitkomsten[positie] = 201
                except UploadFout as fout:
                    uitkomsten[positie] = fout.status_code
            return "bericht"

        dienst = BonDienst(w.root, verstuur=verstuur, haal=w._haal, nu=lambda: START)

        try:
            dienst.uploaden(1, "a.pdf", PDF)
        except UploadFout:
            pass

        assert 429 in uitkomsten


class TestOpslagFouten:
    def test_a_full_disk_gives_503_and_leaves_nothing_behind(
        self, w: _Werkplaats, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def vol(pad: Path, inhoud: bytes) -> None:
            pad.write_bytes(inhoud[:3])
            raise OSError(errno.ENOSPC, "geen ruimte")

        monkeypatch.setattr(upload_module, "_schrijf_nieuw", vol)

        with pytest.raises(UploadFout) as fout:
            w.dienst.uploaden(1, "a.pdf", PDF)

        assert (fout.value.status_code, w.bestanden()) == (503, [])

    def test_a_full_disk_has_its_own_error_code(
        self, w: _Werkplaats, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def vol(pad: Path, inhoud: bytes) -> None:
            raise OSError(errno.ENOSPC, "geen ruimte")

        monkeypatch.setattr(upload_module, "_schrijf_nieuw", vol)

        with pytest.raises(UploadFout) as fout:
            w.dienst.uploaden(1, "a.pdf", PDF)

        assert fout.value.error_code == "OPSLAG_NIET_BESCHIKBAAR"

    def test_a_failure_while_writing_the_metadata_leaves_no_temporary_file_behind(
        self, w: _Werkplaats, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def stuk(bron: object, doel: object) -> None:
            raise OSError(errno.EIO, "schijffout")

        monkeypatch.setattr(upload_module.os, "replace", stuk)

        with pytest.raises(UploadFout):
            w.dienst.uploaden(1, "a.pdf", PDF)

        assert w.bestanden() == []

    def test_a_refused_upload_is_logged_with_the_tenant_and_the_code(
        self, w: _Werkplaats, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)

        with pytest.raises(UploadFout):
            w.dienst.uploaden(4, "geheim.exe", PDF)

        assert "tenant=4" in caplog.text and "FILE_TYPE_NOT_ALLOWED" in caplog.text

    def test_the_log_of_a_refusal_has_no_file_name(
        self, w: _Werkplaats, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)

        with pytest.raises(UploadFout):
            w.dienst.uploaden(4, "geheim.exe", PDF)

        assert "geheim" not in caplog.text


class TestHetVerlopen:
    def test_a_finished_order_whose_result_is_gone_shows_the_stored_result_and_not_waiting(
        self, w: _Werkplaats
    ) -> None:
        """Code-review ronde 1: na de bewaartijd van het resultaat was een klare bon nog "wachten".

        Sinds de acceptatie van dag 4 is het resultaat bij de eerste keer ophalen naast de bon vastgelegd; een
        klare bon blijft dus "gelezen" (was: "verlopen"). Zie `test_resultaat_blijft_staan.py`."""
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)
        w.resultaten["bericht-1"] = {
            "status": "gelezen",
            "reden": "",
            "sha256": hashlib.sha256(PDF).hexdigest(),
            "velden": {},
        }
        w.dienst.status(1, bestand_id)
        del w.resultaten["bericht-1"]

        assert w.dienst.status(1, bestand_id)["status"] == "gelezen"

    def test_after_the_result_time_the_status_is_expired_before_the_quota_time(
        self, w: _Werkplaats
    ) -> None:
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)
        w.nu = START + timedelta(seconds=VERLOOP_SECONDEN + 1)

        assert w.dienst.status(1, bestand_id)["status"] == "verlopen"

    def test_just_before_the_result_time_the_status_is_still_waiting(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)
        w.nu = START + timedelta(seconds=VERLOOP_SECONDEN - 1)

        assert w.dienst.status(1, bestand_id)["status"] == "wachten"

    def test_the_result_time_is_shorter_than_the_quota_time(self) -> None:
        assert VERLOOP_SECONDEN < OPENSTAAND_SECONDEN


_GELDIGE_VELDEN: dict[str, object] = {
    "leverancier": "Bakkerij De Korenaar B.V.",
    "datum": "2026-10-01",
    "totaal": "12.10",
    "factuurnummer": "F-2026-001",
    "btw": {"9": "0.50", "21": "1.60"},
    "btw_nummer": "NL123456789B01",
    "kvk_nummer": "12345678",
}


class TestDeVeldenVanDeWorkerWordenGetoetst:
    """Security-review ronde 1: de uitkomst van de worker is niet te vertrouwen, ook niet met de juiste hash."""

    def _lees(self, w: _Werkplaats, velden: object) -> dict[str, object]:
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)
        w.resultaten["bericht-1"] = {
            "status": "gelezen",
            "reden": "",
            "sha256": hashlib.sha256(PDF).hexdigest(),
            "velden": velden,  # type: ignore[dict-item]  # de test geeft bewust ongeldige vormen mee
        }
        return w.dienst.status(1, bestand_id)

    def test_valid_fields_are_shown(self, w: _Werkplaats) -> None:
        antwoord = self._lees(w, dict(_GELDIGE_VELDEN))

        assert (antwoord["status"], antwoord["velden"]) == ("gelezen", _GELDIGE_VELDEN)

    def test_the_longest_values_the_real_worker_can_deliver_are_shown(self, w: _Werkplaats) -> None:
        """Code-review ronde 2: de leverancier is een hele regel (tot 500) en een factuurnummer kan 41+ zijn."""
        velden = {**_GELDIGE_VELDEN, "leverancier": "L" * 500, "factuurnummer": "F" * 64}

        assert self._lees(w, velden)["status"] == "gelezen"

    def test_empty_fields_are_shown(self, w: _Werkplaats) -> None:
        velden = {sleutel: None for sleutel in _GELDIGE_VELDEN}

        assert self._lees(w, velden)["status"] == "gelezen"

    def test_a_subset_of_the_fields_is_shown(self, w: _Werkplaats) -> None:
        assert self._lees(w, {"totaal": "12.10"})["status"] == "gelezen"

    @pytest.mark.parametrize(
        "velden",
        [
            {**_GELDIGE_VELDEN, "onbekend": "x"},
            {**_GELDIGE_VELDEN, "totaal": "abc"},
            {**_GELDIGE_VELDEN, "totaal": 12.1},
            {**_GELDIGE_VELDEN, "totaal": "1" * 30},
            {**_GELDIGE_VELDEN, "datum": "morgen"},
            {**_GELDIGE_VELDEN, "datum": "2026-10-01T00:00"},
            {**_GELDIGE_VELDEN, "datum": "2026-13-45"},
            {**_GELDIGE_VELDEN, "leverancier": "x" * 501},
            {**_GELDIGE_VELDEN, "leverancier": "a\ud800b"},
            {**_GELDIGE_VELDEN, "factuurnummer": "F" * 65},
            {**_GELDIGE_VELDEN, "leverancier": {"a": "b"}},
            {**_GELDIGE_VELDEN, "factuurnummer": ["F1"]},
            {**_GELDIGE_VELDEN, "btw": {"abc": "1.00"}},
            {**_GELDIGE_VELDEN, "btw": {"21": "veel"}},
            {**_GELDIGE_VELDEN, "btw": {str(i): "1.00" for i in range(11)}},
            {**_GELDIGE_VELDEN, "btw": ["21"]},
            {**_GELDIGE_VELDEN, "btw_nummer": "N" * 41},
            {**_GELDIGE_VELDEN, "kvk_nummer": 12345678},
            ["totaal"],
            "totaal",
            12,
        ],
    )
    def test_fields_outside_the_schema_are_not_shown(self, w: _Werkplaats, velden: object) -> None:
        antwoord = self._lees(w, velden)

        assert (antwoord["status"], antwoord.get("velden")) == ("ongeldig", None)

    def test_a_reason_that_cannot_be_sent_as_text_is_left_out(self, w: _Werkplaats) -> None:
        """Een alleenstaande surrogaat gaf een `UnicodeEncodeError` en dus een permanente 500 op de statusroute."""
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)
        w.resultaten["bericht-1"] = {"status": "geweigerd", "reden": "kapot \ud800", "velden": {}}

        antwoord = w.dienst.status(1, bestand_id)

        assert json.dumps(antwoord, ensure_ascii=False).encode("utf-8") and antwoord["reden"] == ""

    def test_a_long_reason_of_the_worker_is_cut_off(self, w: _Werkplaats) -> None:
        bestand_id = w.dienst.uploaden(1, "a.pdf", PDF)
        w.resultaten["bericht-1"] = {"status": "geweigerd", "reden": "r" * 5000, "velden": {}}

        reden = str(w.dienst.status(1, bestand_id)["reden"])

        assert len(reden) <= 200
