"""AUDIT-ARCH-2026-07-02 Dag 2 losse P1 -- INFRA-001 / PLAT-001
(infra-prod-compose-missing-resource-limits, [EXTRA VERIFICATIE VEREIST]).

`docker-compose.prod.yml` had geen `deploy.resources.limits` op de kernservices
(backend, traefik, postgres, redis) -- learning-worker en workflow-worker hadden
al wel limits. Zonder limits kan een enkele container onbeperkt geheugen/CPU
opeisen en de rest van de host verstikken (noisy-neighbor-risico op een
single-host-achtige deployment zoals docker-compose.prod.yml).
"""

from pathlib import Path

import yaml

COMPOSE_FILE = Path("docker-compose.prod.yml").resolve()

CORE_SERVICES_REQUIRING_LIMITS = ("backend",)


def _load_prod_compose() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


def test_backend_service_has_resource_limits() -> None:
    """backend is de kernservice die extern verkeer ontvangt -- vereist een limit
    zodat een verkeerspiek of memory-leak niet de hele host meesleurt."""
    compose = _load_prod_compose()
    backend = compose["services"]["backend"]
    deploy = backend.get("deploy", {})
    limits = deploy.get("resources", {}).get("limits", {})
    assert limits.get("memory"), (
        "backend-service in docker-compose.prod.yml heeft geen deploy.resources."
        "limits.memory (INFRA-001/PLAT-001)"
    )


def test_workers_still_have_resource_limits() -> None:
    """Regressiebeveiliging: learning-worker/workflow-worker hadden al limits --
    deze mogen niet per ongeluk verdwijnen."""
    compose = _load_prod_compose()
    for service_name in ("learning-worker", "workflow-worker"):
        service = compose["services"][service_name]
        limits = service.get("deploy", {}).get("resources", {}).get("limits", {})
        assert limits.get("memory"), f"{service_name} is de bestaande memory-limit kwijtgeraakt"


def test_portal_service_has_resource_limits() -> None:
    """Levend Monument Heritage Portal (ADR-029 P2-6) moet in productie resource limits
    hebben om geheugenuitputting door SSR of static file serving te voorkomen."""
    compose = _load_prod_compose()
    portal = compose["services"]["portal"]
    deploy = portal.get("deploy", {})
    limits = deploy.get("resources", {}).get("limits", {})
    reservations = deploy.get("resources", {}).get("reservations", {})
    assert limits.get("memory") == "512M", "portal service vereist 512M memory limit"
    assert reservations.get("memory") == "128M", "portal service vereist 128M memory reservation"

