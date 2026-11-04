"""Docling, torch en Tesseract zitten alleen in de EIGEN bonlezer-worker (bonlezer dag 2).

Brief `docs/agent-briefs/generated/2026-10-15-sprint-dag-bonlezer-dag2-eigen-worker.md`. Docling haalt
PyTorch en meer binnen en maakt een image ongeveer twee gigabyte zwaarder
(`docs/evidence/bonlezer-meting-2026-10-15.md`, sectie Grootte). Het backend-image mag dat niet
meekrijgen, en de worker die het wel heeft mag niets bereiken behalve Redis.

Bewaakte verzamelingen (benoemd, niet afgeleid):

- `BACKEND_AFHANKELIJKHEDEN`: de requirements-bestanden van het backend-image;
- de STAGES van het `Dockerfile`: alleen `bonlezer-worker` mag Docling, Tesseract of
  `requirements-bonlezer.txt` noemen;
- de DIENSTEN van `docker-compose.yml`: `bonlezer-worker` staat op een intern netwerk, alleen Redis staat
  er nog op, en de uploadmap is alleen-lezen.

De tests lezen de structuur (stages, YAML), niet losse tekst: een woord in een commentaar of onder een
andere service telt niet.

Mutatiebewijs (2026-10-15): per bewaakt element een mutatie in het echte bestand (daarna teruggezet
via een kopie), zie de commitboodschap.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile"
COMPOSE = REPO_ROOT / "docker-compose.yml"

BACKEND_AFHANKELIJKHEDEN = (
    "requirements.txt",
    "requirements-base.txt",
    "requirements-prod.txt",
    "requirements-prod.lock",
)
VERBODEN_PAKKET = re.compile(
    r"^\s*(?:docling|pytesseract|tesserocr|rapidocr|easyocr)\b", re.IGNORECASE
)
VERBODEN_IN_STAGE = re.compile(r"docling|tesseract|requirements-bonlezer", re.IGNORECASE)

DOEL = "bonlezer-worker"
INTERN_NETWERK = "bonlezer_intern"
KOPPEL_NETWERK = "bonlezer_koppel"
BROKER = "src.core.als.bonlezer.worker:_broker"


def _stages() -> dict[str, str]:
    """{stagenaam: tekst} uit het Dockerfile, zonder commentaarregels."""
    uit: dict[str, list[str]] = {}
    huidig: str | None = None
    for regel in DOCKERFILE.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n"):
        treffer = re.match(r"\s*FROM\s+\S+\s+AS\s+([\w-]+)", regel, re.IGNORECASE)
        if treffer:
            huidig = str(treffer.group(1))
            uit[huidig] = []
        if huidig is not None and not regel.lstrip().startswith("#"):
            uit[huidig].append(regel)
    return {naam: "\n".join(regels) for naam, regels in uit.items()}


def _compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _diensten() -> dict[str, dict[str, Any]]:
    return _compose().get("services", {})


def test_the_scan_sees_the_files_and_stages_it_should() -> None:
    """Controlegroep: de benoemde bestanden bestaan en het Dockerfile heeft de verwachte stages."""
    ontbreekt = [f for f in BACKEND_AFHANKELIJKHEDEN if not (REPO_ROOT / f).exists()]
    stages = _stages()

    assert ontbreekt == [] and {"base", "dependencies", "production-api", DOEL} <= set(stages)


@pytest.mark.parametrize("bestand", BACKEND_AFHANKELIJKHEDEN)
def test_the_backend_requirements_do_not_contain_the_reading_packages(bestand: str) -> None:
    regels = (REPO_ROOT / bestand).read_text(encoding="utf-8").splitlines()
    gevonden = [r.strip() for r in regels if VERBODEN_PAKKET.match(r)]

    assert gevonden == [], f"{bestand} bevat leespakketten voor de bonlezer-worker: {gevonden}"


def test_only_the_bonlezer_worker_stage_mentions_docling_or_tesseract() -> None:
    gevonden = {
        naam: sorted({m.lower() for m in VERBODEN_IN_STAGE.findall(tekst)})
        for naam, tekst in _stages().items()
        if naam != DOEL and VERBODEN_IN_STAGE.search(tekst)
    }

    assert gevonden == {}, f"deze stages noemen leespakketten buiten {DOEL}: {gevonden}"


def test_no_other_stage_is_built_on_the_bonlezer_worker() -> None:
    tekst = DOCKERFILE.read_text(encoding="utf-8")

    assert not re.search(rf"FROM\s+{DOEL}\b", tekst), "een ander doel bouwt op de bonlezer-worker"


class TestHetDockerfileDoel:
    def test_the_stage_installs_the_pinned_requirements_and_the_dutch_model(self) -> None:
        stage = _stages()[DOEL]

        assert "requirements-bonlezer.txt" in stage and "tesseract-ocr-nld" in stage

    def test_the_stage_downloads_the_models_so_that_reading_needs_no_network(self) -> None:
        assert "docling-tools models download" in _stages()[DOEL]

    def test_the_stage_runs_as_a_non_root_user(self) -> None:
        assert re.search(r"^USER\s+appuser\s*$", _stages()[DOEL], re.MULTILINE)

    def test_the_stage_starts_dramatiq_on_the_named_broker(self) -> None:
        stage = _stages()[DOEL]

        assert "ENTRYPOINT" in stage and BROKER in stage


class TestDeComposeDienst:
    def test_the_service_exists_and_is_built_from_the_own_target(self) -> None:
        dienst = _diensten()["bonlezer-worker"]

        assert dienst["build"]["target"] == DOEL

    def test_the_service_is_on_the_internal_network_and_nowhere_else(self) -> None:
        assert _diensten()["bonlezer-worker"]["networks"] == [INTERN_NETWERK]

    def test_the_internal_network_has_no_outgoing_traffic(self) -> None:
        assert _compose()["networks"][INTERN_NETWERK].get("internal") is True

    def test_the_main_redis_is_not_on_the_internal_network(self) -> None:
        """Dag 3 (besluit regie): de worker deelt geen Redis meer met de rest van de stack."""
        assert INTERN_NETWERK not in _diensten()["redis"]["networks"]

    def test_the_own_redis_is_on_both_internal_networks_and_nowhere_else(self) -> None:
        assert _diensten()["bonlezer-redis"]["networks"] == [INTERN_NETWERK, KOPPEL_NETWERK]

    def test_the_coupling_network_has_no_outgoing_traffic(self) -> None:
        assert _compose()["networks"][KOPPEL_NETWERK].get("internal") is True

    def test_the_worker_is_not_on_the_coupling_network(self) -> None:
        """Security-review ronde 1: op hetzelfde netwerk zag de worker `backend:8000` rechtstreeks."""
        assert KOPPEL_NETWERK not in _diensten()["bonlezer-worker"]["networks"]

    def test_the_backend_is_not_on_the_network_of_the_worker(self) -> None:
        assert INTERN_NETWERK not in _diensten()["backend"]["networks"]

    def test_the_own_redis_has_a_memory_limit_and_does_not_evict(self) -> None:
        opdracht = shlex.split(str(_diensten()["bonlezer-redis"]["command"]))

        assert opdracht[opdracht.index("--maxmemory") + 1] == "256mb" and (
            opdracht[opdracht.index("--maxmemory-policy") + 1] == "noeviction"
        )

    def test_the_own_redis_has_a_container_memory_limit(self) -> None:
        limiet = _diensten()["bonlezer-redis"]["deploy"]["resources"]["limits"]["memory"]

        assert limiet in {"384M", "512M"}

    def test_the_backend_has_a_timeout_for_the_own_redis(self) -> None:
        """Een worker die Redis pauzeert mag de threadpool van de backend niet laten vollopen."""
        omgeving = [str(e) for e in _diensten()["backend"]["environment"]]

        assert "BONLEZER_SOCKET_TIMEOUT=5" in omgeving

    def test_the_own_redis_publishes_no_port(self) -> None:
        assert "ports" not in _diensten()["bonlezer-redis"]

    def test_the_own_redis_requires_a_password_without_fallback(self) -> None:
        opdracht = shlex.split(str(_diensten()["bonlezer-redis"]["command"]))

        assert opdracht[opdracht.index("--requirepass") + 1].startswith(
            "${BONLEZER_REDIS_PASSWORD:?"
        )

    def test_the_own_redis_does_not_use_the_main_redis_password(self) -> None:
        assert "${REDIS_PASSWORD" not in str(_diensten()["bonlezer-redis"])

    def test_the_own_redis_does_not_write_the_queue_or_the_results_to_disk(self) -> None:
        """Resultaten bevatten velden van een bon; zonder AOF of snapshot blijft er niets achter."""
        opdracht = shlex.split(str(_diensten()["bonlezer-redis"]["command"]))

        assert (
            opdracht[opdracht.index("--appendonly") + 1] == "no"
            and opdracht[opdracht.index("--save") + 1] == ""
        )

    def test_only_the_expected_services_are_on_the_internal_network(self) -> None:
        erop = sorted(
            naam
            for naam, dienst in _diensten().items()
            if INTERN_NETWERK in (dienst.get("networks") or [])
        )

        assert erop == ["bonlezer-redis", "bonlezer-worker"]

    def test_only_the_backend_and_the_own_redis_are_on_the_coupling_network(self) -> None:
        erop = sorted(
            naam
            for naam, dienst in _diensten().items()
            if KOPPEL_NETWERK in (dienst.get("networks") or [])
        )

        assert erop == ["backend", "bonlezer-redis"]

    def test_the_backend_keeps_its_own_network_next_to_the_coupling_one(self) -> None:
        assert _diensten()["backend"]["networks"] == ["sanskritisetu_network", KOPPEL_NETWERK]

    def test_the_backend_writes_to_the_upload_volume_and_the_worker_only_reads_it(self) -> None:
        backend = [str(v) for v in _diensten()["backend"].get("volumes", [])]

        assert "bonlezer_uploads:/data/bonnen" in backend

    def test_the_backend_names_the_broker_of_the_own_redis(self) -> None:
        omgeving = [str(e) for e in _diensten()["backend"]["environment"]]

        assert any(
            e.startswith("BONLEZER_BROKER_URL=") and "@bonlezer-redis:6379" in e for e in omgeving
        )

    def test_the_service_publishes_no_port(self) -> None:
        assert "ports" not in _diensten()["bonlezer-worker"]

    def test_every_volume_of_the_service_is_read_only(self) -> None:
        volumes = [str(v) for v in _diensten()["bonlezer-worker"].get("volumes", [])]

        assert volumes != [] and all(v.endswith(":ro") for v in volumes)

    def test_the_service_names_the_broker_and_not_only_the_module(self) -> None:
        assert _diensten()["bonlezer-worker"]["command"][0] == BROKER

    def test_the_service_drops_every_capability_and_blocks_privilege_gain(self) -> None:
        dienst = _diensten()["bonlezer-worker"]

        assert dienst["cap_drop"] == ["ALL"] and "no-new-privileges:true" in dienst["security_opt"]

    def test_the_service_does_not_depend_on_the_database(self) -> None:
        """Geen tabel en geen migratie: de worker heeft de database niet nodig (en zit er niet naast)."""
        dienst = _diensten()["bonlezer-worker"]

        assert "postgres" not in (dienst.get("depends_on") or {})

    def test_the_service_has_no_database_url(self) -> None:
        omgeving = _diensten()["bonlezer-worker"].get("environment", [])

        assert not any("DATABASE_URL" in str(e) for e in omgeving)

    def test_the_service_logs_in_to_its_own_redis_with_its_own_password(self) -> None:
        omgeving = [str(e) for e in _diensten()["bonlezer-worker"]["environment"]]
        url = next(e for e in omgeving if e.startswith("BONLEZER_BROKER_URL="))

        assert "${BONLEZER_REDIS_PASSWORD:?" in url and "@bonlezer-redis:6379" in url

    def test_the_service_has_no_url_of_the_main_redis(self) -> None:
        tekst = str(_diensten()["bonlezer-worker"])

        assert "${REDIS_PASSWORD" not in tekst and "@redis:6379" not in tekst

    def test_the_service_waits_for_its_own_redis(self) -> None:
        assert "bonlezer-redis" in _diensten()["bonlezer-worker"]["depends_on"]

    def test_the_main_redis_has_no_user_for_the_worker_anymore(self) -> None:
        assert "--user" not in str(_diensten()["redis"]["command"])

    def test_the_healthcheck_uses_only_tools_that_exist_in_the_image(self) -> None:
        """Gemeten 2026-10-15: `pgrep` zit niet in het image (`command -v pgrep` geeft niets)."""
        controle = " ".join(str(d) for d in _diensten()["bonlezer-worker"]["healthcheck"]["test"])

        assert "pgrep" not in controle and "python" in controle

    def test_the_service_restarts_after_a_crash(self) -> None:
        assert _diensten()["bonlezer-worker"]["restart"] == "unless-stopped"

    def test_the_service_limits_the_number_of_processes(self) -> None:
        assert 0 < int(_diensten()["bonlezer-worker"]["pids_limit"]) <= 512

    def test_the_broker_password_has_no_fallback(self) -> None:
        omgeving = [str(e) for e in _diensten()["bonlezer-worker"]["environment"]]

        assert any("BONLEZER_REDIS_PASSWORD:?" in e for e in omgeving)
