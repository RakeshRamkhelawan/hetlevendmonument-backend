"""Architectuurtests voor Levend Monument Portaal Docker Compose & Traefik v3 Routing (ADR-029 P2-6).

Valideert:
- Aanwezigheid en configuratie van `portal` in docker-compose.yml, docker-compose.prod.yml en docker-compose.dev.yml.
- Traefik router prioriteitshiërarchie: backend (100) > portal (10) > frontend (1).
- Router matching regels: apex domeinen, alternatieve spelling, www en Go regex subdomeinen.
- Service port 5174 en security-headers middleware binding.
- Productie resource limits (512M limit, 128M reservation).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_BASE = REPO_ROOT / "docker-compose.yml"
COMPOSE_PROD = REPO_ROOT / "docker-compose.prod.yml"
COMPOSE_DEV = REPO_ROOT / "docker-compose.dev.yml"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _extract_label_value(labels: list[str], prefix: str) -> str | None:
    for label in labels:
        if label.startswith(prefix):
            return label[len(prefix) :].strip("=")
    return None


@pytest.mark.unit
def test_portal_present_in_base_dev_and_prod_compose() -> None:
    """Verifieert dat de portal service in alle drie de compose-omgevingen gedefinieerd is."""
    base = _load_yaml(COMPOSE_BASE)
    prod = _load_yaml(COMPOSE_PROD)
    dev = _load_yaml(COMPOSE_DEV)

    assert "portal" in base["services"], "portal ontbreekt in docker-compose.yml"
    assert "portal" in prod["services"], "portal ontbreekt in docker-compose.prod.yml"
    assert "portal" in dev["services"], "portal ontbreekt in docker-compose.dev.yml"

    # Port exposure contract (5174)
    base_ports = base["services"]["portal"].get("ports", [])
    dev_ports = dev["services"]["portal"].get("ports", [])
    assert any("5174" in p for p in base_ports), "docker-compose.yml moet poort 5174 binden"
    assert any("5174" in p for p in dev_ports), "docker-compose.dev.yml moet poort 5174 binden"


@pytest.mark.unit
def test_traefik_router_priority_hierarchy_contract() -> None:
    """Verifieert het router-prioriteitscontract: backend (100) > portal (10) > frontend (1).
    
    Dit voorkomt dat de SPA-catchall de API-requests (/api/v1/...) naar hetzelfde domein onderschept.
    """
    base = _load_yaml(COMPOSE_BASE)
    services = base["services"]

    backend_labels = services["backend"].get("labels", [])
    portal_labels = services["portal"].get("labels", [])
    frontend_labels = services["frontend"].get("labels", [])

    backend_priority_str = _extract_label_value(
        backend_labels, "traefik.http.routers.backend.priority"
    )
    portal_priority_str = _extract_label_value(
        portal_labels, "traefik.http.routers.portal.priority"
    )
    frontend_priority_str = _extract_label_value(
        frontend_labels, "traefik.http.routers.frontend.priority"
    )

    assert backend_priority_str is not None, "backend router mist expliciete priority label"
    assert portal_priority_str is not None, "portal router mist expliciete priority label"
    assert frontend_priority_str is not None, "frontend router mist expliciete priority label"

    backend_priority = int(backend_priority_str)
    portal_priority = int(portal_priority_str)
    frontend_priority = int(frontend_priority_str)

    assert backend_priority > portal_priority, (
        f"Backend priority ({backend_priority}) moet HOGER zijn dan portal priority ({portal_priority})"
    )
    assert portal_priority > frontend_priority, (
        f"Portal priority ({portal_priority}) moet HOGER zijn dan frontend priority ({frontend_priority})"
    )


@pytest.mark.unit
def test_traefik_portal_routing_rules_cover_domains_and_subdomains() -> None:
    """Verifieert dat de portal routing regels alle domeinen en erfgoedsubdomeinen dekken."""
    base = _load_yaml(COMPOSE_BASE)
    prod = _load_yaml(COMPOSE_PROD)
    dev = _load_yaml(COMPOSE_DEV)

    for name, compose in [("base", base), ("prod", prod)]:
        labels = compose["services"]["portal"].get("labels", [])
        rule = _extract_label_value(labels, "traefik.http.routers.portal.rule")
        assert rule is not None, f"portal in {name} mist traefik rule label"

        # Domein coverage
        assert "Host(`levendmonument.nl`)" in rule, f"{name} mist levendmonument.nl"
        assert "Host(`www.levendmonument.nl`)" in rule, f"{name} mist www.levendmonument.nl"
        assert "Host(`levend-monument.nl`)" in rule, f"{name} mist levend-monument.nl"
        assert "Host(`www.levend-monument.nl`)" in rule, f"{name} mist www.levend-monument.nl"
        assert "Host(`portal.sanskritisetu.org`)" in rule, f"{name} mist portal.sanskritisetu.org"

        # Traefik v3 Go Regexp subdomeinen (zonder v2 named regex)
        assert "HostRegexp(`^[a-z0-9-]+\\.levendmonument\\.nl$$`)" in rule, (
            f"{name} mist Go regexp voor levendmonument.nl subdomeinen"
        )
        assert "HostRegexp(`^[a-z0-9-]+\\.levend-monument\\.nl$$`)" in rule, (
            f"{name} mist Go regexp voor levend-monument.nl subdomeinen"
        )

    # Dev router coverage
    dev_labels = dev["services"]["portal"].get("labels", [])
    dev_rule = _extract_label_value(dev_labels, "traefik.http.routers.portal-dev.rule")
    assert dev_rule is not None, "dev portal mist portal-dev.rule label"
    assert "Host(`portal.localhost`)" in dev_rule
    assert "Host(`monument.local`)" in dev_rule
    assert "HostRegexp(`^[a-z0-9-]+\\.monument\\.local$$`)" in dev_rule


@pytest.mark.unit
def test_traefik_portal_service_port_and_middleware() -> None:
    """Verifieert dat de loadbalancer poort 5174 is en security headers actief zijn."""
    base = _load_yaml(COMPOSE_BASE)
    prod = _load_yaml(COMPOSE_PROD)

    for name, compose in [("base", base), ("prod", prod)]:
        labels = compose["services"]["portal"].get("labels", [])
        port = _extract_label_value(
            labels, "traefik.http.services.portal-svc.loadbalancer.server.port"
        )
        middlewares = _extract_label_value(labels, "traefik.http.routers.portal.middlewares")

        assert port == "5174", f"{name} portal loadbalancer port moet 5174 zijn"
        assert middlewares is not None and "security-headers" in middlewares, (
            f"{name} portal moet security-headers middleware bevatten"
        )


@pytest.mark.unit
def test_portal_production_build_and_resources() -> None:
    """Verifieert productie build context, target en resource limits."""
    prod = _load_yaml(COMPOSE_PROD)
    portal = prod["services"]["portal"]

    build_cfg = portal.get("build", {})
    assert build_cfg.get("target") == "production", "prod portal build target moet production zijn"
    assert build_cfg.get("args", {}).get("VITE_API_URL") == "/api/v1", (
        "prod portal VITE_API_URL moet relatief /api/v1 zijn voor multi-tenant domeinresolutie"
    )

    deploy = portal.get("deploy", {})
    resources = deploy.get("resources", {})
    assert resources.get("limits", {}).get("memory") == "512M", "prod portal mist 512M memory limit"
    assert resources.get("reservations", {}).get("memory") == "128M", (
        "prod portal mist 128M memory reservation"
    )


@pytest.mark.integration
def test_docker_compose_config_validation() -> None:
    """Draait docker compose config voor zowel dev als prod om te garanderen dat de YAML
    volledig syntactisch valide is en compose geen fouten geeft."""
    # docker-compose.yml verplicht sinds 38c16e98f een aantal env vars via
    # `${VAR:?...}` (fail-closed bij ontbrekende secrets). `docker compose config`
    # interpoleert die ook voor de DEV-stack, dus de test moet overal dummies
    # meegeven -- niet alleen bij prod.
    dummy_env = os.environ.copy()
    dummy_env.update(
        {
            "POSTGRES_PASSWORD": "test_password",
            "REDIS_PASSWORD": "test_redis_password",
            "SYNC_WEBHOOK_SECRET": "test_sync_webhook_secret",
            "AP_ENCRYPTION_KEY": "test_ap_encryption_key",
            "AP_JWT_SECRET": "test_ap_jwt_secret",
            "AP_WORKER_TOKEN": "test_ap_worker_token",
            "GRAFANA_ADMIN_PASSWORD": "test_grafana_admin_pw",
            "MASTER_ENCRYPTION_KEY": "12345678901234567890123456789012",
            "DATABASE_URL": "postgresql+asyncpg://postgres:test@postgres:5432/sanskritisetu",
            "REDIS_URL": "redis://:test@redis:6379/0",
            "DRAMATIQ_BROKER_URL": "redis://:test@redis:6379/1",
            "TOOL_PAYLOAD_PSEUDONYM_KEY": "12345678901234567890123456789012",
            "DEFAULT_ADMIN_PASSWORD": "test_admin_pw",
            "LLM_PROVIDER": "deepseek",
            "DEFAULT_LLM_MODEL": "deepseek-chat",
            "DEEPSEEK_API_KEY": "sk-test",
            # Sinds de sync van 2026-11-01 verplicht in docker-compose.prod.yml (upstream).
            "FRONTEND_URL": "https://portal.example.test",
            "MISTRAL_API_KEY": "test",
        }
    )
    # 1. Dev config
    dev_res = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_BASE), "-f", str(COMPOSE_DEV), "config"],
        env=dummy_env,
        capture_output=True,
        text=True,
    )
    assert dev_res.returncode == 0, f"docker-compose.dev.yml config fout: {dev_res.stderr}"

    # 2. Prod config (met dummy verplichte credentials)
    prod_res = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_BASE), "-f", str(COMPOSE_PROD), "config"],
        env=dummy_env,
        capture_output=True,
        text=True,
    )
    assert prod_res.returncode == 0, f"docker-compose.prod.yml config fout: {prod_res.stderr}"
