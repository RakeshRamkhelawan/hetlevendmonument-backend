"""De bonlezer-worker leest alleen uit de uploadmap van de EIGEN tenant (bonlezer dag 2).

Brief `docs/agent-briefs/generated/2026-10-15-sprint-dag-bonlezer-dag2-eigen-worker.md`. De actor
`lees_bon(tenant_id, bestand_id)` krijgt een tenant en een bestandsnummer van de backend en leest
`<uploadmap>/<tenant_id>/<bestand_id>`. Dit bestand toetst de VERWERKING (`verwerk_opdracht`) met een
nagemaakte lezer: wat hier wordt gemeten is welk bestand er wordt geopend, hoe, en wat er gelogd wordt;
het lezen zelf (Docling) is dag 1 en staat in `scripts/bonlezer_meting.py`.

Wat NIET wordt gezegd: dat de worker draait in een container met alleen Redis als buur; dat staat in
`docs/evidence/bonlezer-worker-2026-10-15.md`. En: een symlink-test slaat over waar het
besturingssysteem geen symlinks toestaat (Windows zonder ontwikkelaarsmodus).

Mutatiebewijs (2026-10-15): zie de commitboodschap.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.als.bonlezer import worker as worker_module
from src.core.als.bonlezer.worker import lees_bon, verwerk_opdracht

SET = Path(__file__).resolve().parents[2] / "fixtures" / "bonnen"
BESTAND_ID = "0123456789abcdef0123456789abcdef.pdf"
ANDER_ID = "fedcba9876543210fedcba9876543210.pdf"
PDF = b"%PDF-1.4\n% een proefbestand\n"


class _NagemaakteLezer:
    """Geeft vaste tekst terug en onthoudt welk pad en welke inhoud het kreeg."""

    def __init__(self, tekst: str = "TOTAAL 1,00\n", *, voor_het_lezen: object = None) -> None:
        self.tekst = tekst
        self.paden: list[Path] = []
        self.inhoud: list[bytes] = []
        self.voor_het_lezen = voor_het_lezen

    def lees(self, pad: Path) -> str:
        if callable(self.voor_het_lezen):
            self.voor_het_lezen()
        self.paden.append(pad)
        self.inhoud.append(pad.read_bytes())
        return self.tekst


def _zet(root: Path, tenant: int, naam: str = BESTAND_ID, inhoud: bytes = PDF) -> Path:
    map_ = root / str(tenant)
    map_.mkdir(parents=True, exist_ok=True)
    pad = map_ / naam
    pad.write_bytes(inhoud)
    return pad


def _symlink(bron: Path, doel: Path, *, map_: bool = False) -> None:
    try:
        os.symlink(doel, bron, target_is_directory=map_)
    except (OSError, NotImplementedError):
        pytest.skip("dit besturingssysteem staat hier geen symlinks toe")


class TestAlleenDeEigenTenant:
    def test_a_file_in_the_own_tenant_folder_is_read(self, tmp_path: Path) -> None:
        _zet(tmp_path, 1)

        uitkomst = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=_NagemaakteLezer())

        assert uitkomst["status"] == "gelezen"

    def test_the_result_carries_the_hash_of_the_bytes_that_were_read(self, tmp_path: Path) -> None:
        _zet(tmp_path, 1)

        uitkomst = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=_NagemaakteLezer())

        assert uitkomst["sha256"] == hashlib.sha256(PDF).hexdigest()

    def test_the_same_file_name_in_another_tenant_folder_is_not_found(self, tmp_path: Path) -> None:
        _zet(tmp_path, 2)

        uitkomst = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=_NagemaakteLezer())

        assert uitkomst["status"] == "geweigerd"

    def test_the_reader_is_not_called_for_another_tenants_file(self, tmp_path: Path) -> None:
        _zet(tmp_path, 2)
        lezer = _NagemaakteLezer()

        verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=lezer)

        assert lezer.paden == []

    @pytest.mark.parametrize(
        "bestand_id",
        [
            f"../2/{BESTAND_ID}",
            f"..\\2\\{BESTAND_ID}",
            f"2/{BESTAND_ID}",
            "/etc/passwd",
            "bon.pdf",
            BESTAND_ID.upper(),
            BESTAND_ID + ".exe",
            "",
            BESTAND_ID + "\x00",
        ],
    )
    def test_a_file_id_that_is_not_one_of_ours_is_refused(
        self, tmp_path: Path, bestand_id: str
    ) -> None:
        _zet(tmp_path, 2)
        _zet(tmp_path, 1)

        uitkomst = verwerk_opdracht(tmp_path, 1, bestand_id, lezer=_NagemaakteLezer())

        assert uitkomst["status"] == "geweigerd"

    @pytest.mark.parametrize("tenant", [0, -1, True, "1", 1.5, None])
    def test_a_tenant_that_is_not_a_positive_whole_number_is_refused(
        self, tmp_path: Path, tenant: object
    ) -> None:
        _zet(tmp_path, 1)

        uitkomst = verwerk_opdracht(tmp_path, tenant, BESTAND_ID, lezer=_NagemaakteLezer())  # type: ignore[arg-type]

        assert uitkomst["status"] == "geweigerd"

    def test_a_missing_file_and_another_tenants_file_look_the_same(self, tmp_path: Path) -> None:
        """Geen bestaan prijsgeven: dezelfde uitkomst als er niets staat."""
        _zet(tmp_path, 2, ANDER_ID)

        weg = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=_NagemaakteLezer())
        andermans = verwerk_opdracht(tmp_path, 1, ANDER_ID, lezer=_NagemaakteLezer())

        assert (weg["status"], weg["reden"]) == (andermans["status"], andermans["reden"])


class TestGeenSymlinks:
    def test_a_symlinked_file_in_the_upload_folder_is_not_followed(self, tmp_path: Path) -> None:
        buiten = tmp_path / "buiten.pdf"
        buiten.write_bytes(PDF)
        (tmp_path / "1").mkdir()
        _symlink(tmp_path / "1" / BESTAND_ID, buiten)
        lezer = _NagemaakteLezer()

        uitkomst = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=lezer)

        assert (uitkomst["status"], lezer.paden) == ("geweigerd", [])

    def test_a_symlinked_tenant_folder_is_not_followed(self, tmp_path: Path) -> None:
        _zet(tmp_path, 2)
        _symlink(tmp_path / "1", tmp_path / "2", map_=True)
        lezer = _NagemaakteLezer()

        uitkomst = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=lezer)

        assert (uitkomst["status"], lezer.paden) == ("geweigerd", [])

    def test_a_folder_in_place_of_the_file_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / "1" / BESTAND_ID).mkdir(parents=True)

        uitkomst = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=_NagemaakteLezer())

        assert uitkomst["status"] == "geweigerd"


class TestDeControlesZonderEchteSymlinks:
    """Mutatiebewijs dag 2 (regie): de koppelingscontroles en de verwisselcontrole moesten rood kunnen.

    De symlink-tests hierboven slaan over op Windows zonder ontwikkelaarsmodus, en dan bleven drie
    mutaties (koppelingscontrole van de tenantmap, van het bestand, en de verwisselcontrole) groen.
    Hier wordt het oordeel van de worker zelf gestuurd (`_is_koppeling`, `os.fstat`), zodat dezelfde
    controles op elk besturingssysteem draaien.
    """

    def test_a_tenant_folder_that_counts_as_a_link_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _zet(tmp_path, 1)
        monkeypatch.setattr(worker_module, "_is_koppeling", lambda s: stat.S_ISDIR(s.st_mode))
        lezer = _NagemaakteLezer()

        uitkomst = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=lezer)

        assert (uitkomst["status"], lezer.paden) == ("geweigerd", [])

    def test_a_file_that_counts_as_a_link_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _zet(tmp_path, 1)
        monkeypatch.setattr(worker_module, "_is_koppeling", lambda s: stat.S_ISREG(s.st_mode))
        lezer = _NagemaakteLezer()

        uitkomst = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=lezer)

        assert (uitkomst["status"], lezer.paden) == ("geweigerd", [])

    def test_a_file_swapped_between_checking_and_opening_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _zet(tmp_path, 1)
        echte_fstat = os.fstat

        def andere_inode(beschrijver: int) -> SimpleNamespace:
            echt = echte_fstat(beschrijver)
            return SimpleNamespace(
                st_mode=echt.st_mode,
                st_size=echt.st_size,
                st_dev=echt.st_dev,
                st_ino=echt.st_ino + 1,
            )

        monkeypatch.setattr(worker_module.os, "fstat", andere_inode)
        lezer = _NagemaakteLezer()

        uitkomst = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=lezer)

        assert (uitkomst["status"], lezer.paden) == ("geweigerd", [])

    def test_the_size_check_on_the_descriptor_refuses_before_any_byte_is_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(worker_module, "MAX_BYTES", 10)
        _zet(tmp_path, 1)
        gelezen: list[int] = []
        monkeypatch.setattr(worker_module, "_lees_bytes", lambda b: gelezen.append(b) or b"")

        verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=_NagemaakteLezer())

        assert gelezen == []

    def test_the_read_itself_is_bounded_when_the_reported_size_is_too_small(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(worker_module, "MAX_BYTES", 10)
        _zet(tmp_path, 1)
        echte_fstat = os.fstat

        def klein(beschrijver: int) -> SimpleNamespace:
            echt = echte_fstat(beschrijver)
            return SimpleNamespace(
                st_mode=echt.st_mode, st_size=0, st_dev=echt.st_dev, st_ino=echt.st_ino
            )

        monkeypatch.setattr(worker_module.os, "fstat", klein)
        lezer = _NagemaakteLezer()

        uitkomst = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=lezer)

        assert (uitkomst["status"], lezer.paden) == ("geweigerd", [])

    def test_the_private_copy_is_created_with_mode_0600(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _zet(tmp_path, 1)
        echte_open = os.open
        modi: list[int] = []

        def noteer(pad: object, vlaggen: int, mode: int = 0o777) -> int:
            if vlaggen & os.O_CREAT:
                modi.append(mode)
            return echte_open(pad, vlaggen, mode)  # type: ignore[arg-type]

        monkeypatch.setattr(worker_module.os, "open", noteer)

        verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=_NagemaakteLezer())

        assert modi == [0o600]

    @pytest.mark.parametrize("tenant", [0, -1, True])
    def test_a_tenant_that_is_not_positive_is_refused_even_when_such_a_folder_exists(
        self, tmp_path: Path, tenant: object
    ) -> None:
        """Een map `0`, `-1` of `True` met het bestand erin: de controle moet VOOR het pad weigeren."""
        _zet(tmp_path, tenant)  # type: ignore[arg-type]
        lezer = _NagemaakteLezer()

        uitkomst = verwerk_opdracht(tmp_path, tenant, BESTAND_ID, lezer=lezer)  # type: ignore[arg-type]

        assert (uitkomst["status"], uitkomst["reden"], lezer.paden) == (
            "geweigerd",
            "ongeldige opdracht",
            [],
        )


class TestHetBestandWordtEenKeerGelezen:
    """TOCTOU (Gate 2 dag 1): wat gecontroleerd en gehasht is, is wat er gelezen wordt."""

    def test_the_reader_gets_a_private_copy_and_not_the_upload_path(self, tmp_path: Path) -> None:
        upload = _zet(tmp_path, 1)
        lezer = _NagemaakteLezer()

        verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=lezer)

        assert lezer.paden[0] != upload and tmp_path not in lezer.paden[0].parents

    def test_a_change_to_the_upload_after_reading_does_not_reach_the_reader(
        self, tmp_path: Path
    ) -> None:
        upload = _zet(tmp_path, 1)
        lezer = _NagemaakteLezer(
            voor_het_lezen=lambda: upload.write_bytes(b"%PDF-1.4\nverwisseld\n")
        )

        uitkomst = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=lezer)

        assert (lezer.inhoud[0], uitkomst["sha256"]) == (PDF, hashlib.sha256(PDF).hexdigest())

    def test_the_private_copy_is_removed_afterwards(self, tmp_path: Path) -> None:
        _zet(tmp_path, 1)
        lezer = _NagemaakteLezer()

        verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=lezer)

        assert not lezer.paden[0].exists()

    def test_a_file_over_the_size_limit_is_refused_without_reading_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(worker_module, "MAX_BYTES", 10)
        _zet(tmp_path, 1)
        lezer = _NagemaakteLezer()

        uitkomst = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=lezer)

        assert (uitkomst["status"], lezer.paden) == ("geweigerd", [])


class TestHetLogEnHetResultaat:
    GEHEIM = "GEHEIMEBONTEKST-Jansen-NL00INGB0123456789"

    def test_the_log_has_tenant_hash_and_status(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        _zet(tmp_path, 7)
        caplog.set_level(logging.INFO)

        verwerk_opdracht(tmp_path, 7, BESTAND_ID, lezer=_NagemaakteLezer())

        tekst = caplog.text
        assert all(
            deel in tekst
            for deel in ("tenant=7", hashlib.sha256(PDF).hexdigest(), "status=gelezen")
        )

    def test_the_log_has_no_text_of_the_receipt(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        _zet(tmp_path, 7)
        caplog.set_level(logging.DEBUG)
        lezer = _NagemaakteLezer(f"TOTAAL 5,00\n{self.GEHEIM}\n")

        verwerk_opdracht(tmp_path, 7, BESTAND_ID, lezer=lezer)

        assert self.GEHEIM not in caplog.text and "TOTAAL" not in caplog.text

    def test_the_log_has_no_text_of_the_receipt_when_reading_fails(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        _zet(tmp_path, 7)
        caplog.set_level(logging.DEBUG)
        geheim = self.GEHEIM

        class _Kapot:
            def lees(self, pad: Path) -> str:
                raise RuntimeError(f"kapot bij {geheim}")

        uitkomst = verwerk_opdracht(tmp_path, 7, BESTAND_ID, lezer=_Kapot())

        assert uitkomst["status"] == "fout" and self.GEHEIM not in caplog.text

    def test_the_result_has_no_text_of_the_receipt(self, tmp_path: Path) -> None:
        _zet(tmp_path, 7)
        lezer = _NagemaakteLezer(f"TOTAAL 5,00\n{self.GEHEIM}\n")

        uitkomst = verwerk_opdracht(tmp_path, 7, BESTAND_ID, lezer=lezer)

        assert self.GEHEIM not in json.dumps(uitkomst)

    def test_a_refusal_is_logged_with_tenant_and_status(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)

        verwerk_opdracht(tmp_path, 3, BESTAND_ID, lezer=_NagemaakteLezer())

        assert "tenant=3" in caplog.text and "status=geweigerd" in caplog.text

    def test_the_log_records_the_duration(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        _zet(tmp_path, 7)
        caplog.set_level(logging.INFO)

        verwerk_opdracht(tmp_path, 7, BESTAND_ID, lezer=_NagemaakteLezer())

        assert "duur_ms=" in caplog.text


class TestDeVeldenKomenMeeAlsJson:
    """De testbonnen door de verwerking, met de brontekst als lezer: dezelfde velden als dag 1."""

    @pytest.mark.parametrize(
        "naam", sorted(p.name.removesuffix(".tekst.txt") for p in SET.glob("*.tekst.txt"))
    )
    def test_the_total_matches_the_answer_for_every_test_document(
        self, tmp_path: Path, naam: str
    ) -> None:
        antwoorden = json.loads((SET / f"{naam}.json").read_text(encoding="utf-8"))
        tekst = (SET / f"{naam}.tekst.txt").read_text(encoding="utf-8")
        _zet(tmp_path, 1)

        uitkomst = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=_NagemaakteLezer(tekst))

        assert uitkomst["velden"]["totaal"] == antwoorden["totaal"]  # type: ignore[index]

    def test_the_vat_per_rate_is_a_json_object(self, tmp_path: Path) -> None:
        _zet(tmp_path, 1)
        lezer = _NagemaakteLezer("TOTAAL 12,10\nBTW 9%  0,50\nBTW 21%  1,60\n")

        uitkomst = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=lezer)

        btw = json.loads(json.dumps(uitkomst))["velden"]["btw"]
        assert btw == {"9": "0.50", "21": "1.60"}


class TestDeFoutenvormen:
    def test_a_reader_that_refuses_the_file_gives_a_refusal(self, tmp_path: Path) -> None:
        from src.core.als.bonlezer.lezer import OngeldigBestand

        class _Weigert:
            def lees(self, pad: Path) -> str:
                raise OngeldigBestand("de inhoud past niet bij de extensie")

        _zet(tmp_path, 1)

        uitkomst = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=_Weigert())

        assert (uitkomst["status"], uitkomst["reden"]) == (
            "geweigerd",
            "de inhoud past niet bij de extensie",
        )

    def test_an_unexpected_error_gives_an_error_without_its_message(self, tmp_path: Path) -> None:
        class _Kapot:
            def lees(self, pad: Path) -> str:
                raise RuntimeError("bevat mogelijk bontekst")

        _zet(tmp_path, 1)

        uitkomst = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=_Kapot())

        assert (uitkomst["status"], uitkomst["reden"]) == ("fout", "RuntimeError")


class TestHetResultaatOphalen:
    """`Message.get_result` gebruikt de GLOBALE broker; de actor bindt bewust aan een eigen broker."""

    def _broker(self) -> object:
        from dramatiq.brokers.stub import StubBroker
        from dramatiq.results import Results
        from dramatiq.results.backends import StubBackend

        broker = StubBroker()
        broker.add_middleware(Results(backend=StubBackend()))
        return broker

    def test_a_stored_result_is_returned(self) -> None:
        import dramatiq

        broker = self._broker()
        bericht = dramatiq.Message(
            queue_name="bonlezer",
            actor_name="lees_bon",
            args=(1, BESTAND_ID),
            kwargs={},
            options={},
        )
        broker.get_results_backend().store_result(bericht, {"status": "gelezen"}, 60_000)  # type: ignore[attr-defined]

        assert worker_module.haal_resultaat(bericht, broker=broker) == {"status": "gelezen"}  # type: ignore[arg-type]

    def test_a_missing_result_without_waiting_raises(self) -> None:
        import dramatiq
        from dramatiq.results import ResultMissing

        bericht = dramatiq.Message(
            queue_name="bonlezer",
            actor_name="lees_bon",
            args=(1, BESTAND_ID),
            kwargs={},
            options={},
        )

        with pytest.raises(ResultMissing):
            worker_module.haal_resultaat(bericht, broker=self._broker())  # type: ignore[arg-type]


class TestDeActor:
    def test_the_actor_listens_on_the_own_queue(self) -> None:
        assert lees_bon.queue_name == "bonlezer"

    def test_the_actor_is_bound_to_its_own_broker(self) -> None:
        assert lees_bon.broker is worker_module._broker

    def test_the_actor_does_not_retry_a_deterministic_refusal(self) -> None:
        assert lees_bon.options.get("max_retries") == 0

    def test_the_upload_root_is_taken_from_the_environment(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("BONLEZER_UPLOAD_ROOT", str(tmp_path))

        assert worker_module.upload_root() == tmp_path


class TestDeBrokerKomtUitDeEigenRedis:
    """Dag 3 (besluit regie): de bonlezer heeft een EIGEN Redis; nooit terugvallen op de hoofd-Redis."""

    def test_the_url_is_taken_from_the_own_variable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BONLEZER_BROKER_URL", "redis://:pw@bonlezer-redis:6379/0")

        assert worker_module.broker_url() == "redis://:pw@bonlezer-redis:6379/0"

    def test_the_url_of_the_main_redis_is_never_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BONLEZER_BROKER_URL", raising=False)
        monkeypatch.setenv("DRAMATIQ_BROKER_URL", "redis://:hoofd@redis:6379/1")
        monkeypatch.setenv("REDIS_URL", "redis://:hoofd@redis:6379/0")

        assert "@redis:" not in worker_module.broker_url()

    def test_the_default_points_at_the_own_redis(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BONLEZER_BROKER_URL", raising=False)

        assert worker_module.broker_url() == "redis://bonlezer-redis:6379/0"

    def test_surrounding_whitespace_is_removed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BONLEZER_BROKER_URL", "  redis://bonlezer-redis:6379/0\n")

        assert worker_module.broker_url() == "redis://bonlezer-redis:6379/0"


class TestTimeoutsVoorDeBackend:
    """Security-review dag 3: een Redis die pauzeert mag de backend niet onbepaald laten wachten."""

    URL = "redis://:pw@bonlezer-redis:6379/0"

    def test_without_the_variable_the_url_has_no_timeouts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BONLEZER_SOCKET_TIMEOUT", raising=False)
        monkeypatch.setenv("BONLEZER_BROKER_URL", self.URL)

        assert worker_module.broker_url() == self.URL

    def test_the_variable_puts_both_timeouts_in_the_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BONLEZER_SOCKET_TIMEOUT", "5")
        monkeypatch.setenv("BONLEZER_BROKER_URL", self.URL)

        assert worker_module.broker_url() == f"{self.URL}?socket_timeout=5&socket_connect_timeout=5"

    def test_a_url_that_already_has_a_query_gets_the_timeouts_added(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BONLEZER_SOCKET_TIMEOUT", "5")
        monkeypatch.setenv("BONLEZER_BROKER_URL", f"{self.URL}?health_check_interval=30")

        assert worker_module.broker_url().endswith(
            "?health_check_interval=30&socket_timeout=5&socket_connect_timeout=5"
        )

    @pytest.mark.parametrize("waarde", ["", "abc", "0", "-1", "nan", "5.5"])
    def test_an_unusable_value_gives_no_timeouts(
        self, monkeypatch: pytest.MonkeyPatch, waarde: str
    ) -> None:
        monkeypatch.setenv("BONLEZER_SOCKET_TIMEOUT", waarde)
        monkeypatch.setenv("BONLEZER_BROKER_URL", self.URL)

        assert worker_module.broker_url() == self.URL

    @staticmethod
    def _timeouts_van_de_echte_clients(omgeving: dict[str, str]) -> dict[str, object]:
        """Importeer de worker in een APART proces en lees de instellingen van de echte verbindingspools.

        Code-review ronde 2: bij `url=` maakt dramatiq zelf een verbindingspool; losse `socket_timeout`-
        argumenten worden dan genegeerd. Alleen de pool van de echte client bewijst dat de time-out werkt.
        """
        import json
        import subprocess
        import sys

        code = (
            "import json\n"
            "from src.core.als.bonlezer import worker as w\n"
            "b = w._broker.client.connection_pool.connection_kwargs\n"
            "r = w._broker.get_results_backend().client.connection_pool.connection_kwargs\n"
            "print(json.dumps({'broker': b.get('socket_timeout'), 'resultaat': r.get('socket_timeout'),"
            " 'verbinden': b.get('socket_connect_timeout')}))\n"
        )
        basis = {k: v for k, v in os.environ.items() if not k.startswith("BONLEZER_")}
        uitvoer = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).resolve().parents[3],
            env={**basis, **omgeving},
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        ).stdout
        return dict(json.loads(uitvoer.strip().splitlines()[-1]))

    def test_the_real_broker_client_has_the_timeouts(self) -> None:
        gezien = self._timeouts_van_de_echte_clients(
            {"BONLEZER_BROKER_URL": self.URL, "BONLEZER_SOCKET_TIMEOUT": "5"}
        )

        assert (gezien["broker"], gezien["verbinden"]) == (5, 5)

    def test_the_real_results_client_has_the_timeouts(self) -> None:
        gezien = self._timeouts_van_de_echte_clients(
            {"BONLEZER_BROKER_URL": self.URL, "BONLEZER_SOCKET_TIMEOUT": "5"}
        )

        assert gezien["resultaat"] == 5

    def test_the_worker_itself_has_no_timeouts(self) -> None:
        gezien = self._timeouts_van_de_echte_clients({"BONLEZER_BROKER_URL": self.URL})

        assert (gezien["broker"], gezien["resultaat"]) == (None, None)


class TestGate2Ronde1:
    """Reparaties na Gate 2 ronde 1 (code-, security-reviewer, 2026-10-15)."""

    def test_the_worker_source_is_ascii_only(self) -> None:
        bron = Path(worker_module.__file__).read_bytes()

        assert [b for b in bron if b > 127] == []

    def test_an_unexpected_error_is_logged_with_its_type_name(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        _zet(tmp_path, 7)
        caplog.set_level(logging.INFO)

        class _Kapot:
            def lees(self, pad: Path) -> str:
                raise ValueError("bevat mogelijk bontekst")

        verwerk_opdracht(tmp_path, 7, BESTAND_ID, lezer=_Kapot())

        assert "reden=ValueError" in caplog.text and "bontekst" not in caplog.text

    def test_the_result_expires_after_an_explicit_time_as_long_as_the_bon_is_kept(self) -> None:
        """Was 300 s (acceptatie dag 4: het resultaat verdween na ~6 minuten); nu de bewaartijd van de bon."""
        assert lees_bon.options.get("result_ttl") == worker_module.RESULTAAT_TTL_MS

    def test_a_refused_order_does_not_load_the_reader(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("BONLEZER_UPLOAD_ROOT", str(tmp_path))
        geladen: list[int] = []
        monkeypatch.setattr(worker_module, "_lezer", lambda: geladen.append(1))

        uitkomst = lees_bon.fn(0, BESTAND_ID)

        assert (uitkomst["status"], geladen) == ("geweigerd", [])

    def test_a_reader_that_cannot_be_created_gives_an_error_result(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("BONLEZER_UPLOAD_ROOT", str(tmp_path))
        _zet(tmp_path, 1)

        def stuk() -> None:
            raise OSError("modellen ontbreken")

        monkeypatch.setattr(worker_module, "_lezer", stuk)

        uitkomst = lees_bon.fn(1, BESTAND_ID)

        assert (uitkomst["status"], uitkomst["reden"]) == ("fout", "OSError")

    def test_a_too_large_file_looks_the_same_as_a_missing_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(worker_module, "MAX_BYTES", 10)
        _zet(tmp_path, 1)

        groot = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=_NagemaakteLezer())
        weg = verwerk_opdracht(tmp_path, 1, ANDER_ID, lezer=_NagemaakteLezer())

        assert (groot["status"], groot["reden"]) == (weg["status"], weg["reden"])

    def test_a_refusal_after_reading_does_not_reveal_the_hash(self, tmp_path: Path) -> None:
        from src.core.als.bonlezer.lezer import OngeldigBestand

        class _Weigert:
            def lees(self, pad: Path) -> str:
                raise OngeldigBestand("de inhoud past niet bij de extensie")

        _zet(tmp_path, 1)

        uitkomst = verwerk_opdracht(tmp_path, 1, BESTAND_ID, lezer=_Weigert())

        assert uitkomst["sha256"] == ""

    def test_hostile_message_options_are_reset_to_fixed_values(self) -> None:
        import dramatiq

        bericht = dramatiq.Message(
            queue_name="bonlezer",
            actor_name="lees_bon",
            args=(1, BESTAND_ID),
            kwargs={},
            options={
                "max_retries": 1000,
                "time_limit": 10**9,
                "result_ttl": 10**12,
                "pipe_target": "x",
                "on_failure": "x",
                "on_success": "x",
            },
        )

        worker_module._VasteOpties().before_process_message(worker_module._broker, bericht)

        assert bericht.options == {
            "max_retries": 0,
            "time_limit": 180_000,
            "result_ttl": worker_module.RESULTAAT_TTL_MS,
        }

    def test_the_fixed_options_keep_the_message_id_and_the_retry_counter(self) -> None:
        import dramatiq

        bericht = dramatiq.Message(
            queue_name="bonlezer",
            actor_name="lees_bon",
            args=(1, BESTAND_ID),
            kwargs={},
            options={"redis_message_id": "abc", "retries": 2, "traceback": "x"},
        )

        worker_module._VasteOpties().before_process_message(worker_module._broker, bericht)

        assert (
            bericht.options["redis_message_id"],
            bericht.options["retries"],
            bericht.options["traceback"],
        ) == ("abc", 2, "x")

    def test_the_fixed_options_run_before_the_time_limit_is_read(self) -> None:
        from dramatiq.middleware import TimeLimit

        soorten = [type(m) for m in worker_module._broker.middleware]

        assert soorten.index(worker_module._VasteOpties) < soorten.index(TimeLimit)

    def test_the_broker_uses_its_own_key_prefix(self) -> None:
        assert worker_module._broker.namespace == "bonlezer"
