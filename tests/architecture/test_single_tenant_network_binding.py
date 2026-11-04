"""AUDIT-ARCH-2026-07-02 Groep 5 -- SEC-ARCH-002 / SEC-INFRA-001 (single-tenant-deel).

docker-compose.single-tenant.yml bond Postgres en Redis op alle interfaces
("5432:5432" / "6379:6379" i.p.v. "127.0.0.1:<poort>:<poort>"), en Redis had
helemaal geen requirepass-configuratie -- erger dan de audit beschreef (zelfs geen
zwakke default-fallback zoals de base docker-compose.yml).
"""

from pathlib import Path

import yaml

COMPOSE_FILE = Path("docker-compose.single-tenant.yml").resolve()


def _load_compose() -> dict:
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    return yaml.safe_load(content)


def test_postgres_port_bound_to_localhost() -> None:
    compose = _load_compose()
    ports = compose["services"]["postgres"].get("ports", [])
    assert ports, "postgres-service in docker-compose.single-tenant.yml heeft geen ports-mapping"
    for port_mapping in ports:
        assert str(port_mapping).startswith("127.0.0.1:"), (
            f"postgres-poort '{port_mapping}' is niet gebonden op 127.0.0.1 -- "
            "bereikbaar vanaf elke netwerkinterface (SEC-INFRA-001)"
        )


def test_redis_port_bound_to_localhost() -> None:
    compose = _load_compose()
    ports = compose["services"]["redis"].get("ports", [])
    assert ports, "redis-service in docker-compose.single-tenant.yml heeft geen ports-mapping"
    for port_mapping in ports:
        assert str(port_mapping).startswith("127.0.0.1:"), (
            f"redis-poort '{port_mapping}' is niet gebonden op 127.0.0.1 -- "
            "bereikbaar vanaf elke netwerkinterface (SEC-ARCH-002)"
        )


def test_redis_requires_authentication() -> None:
    compose = _load_compose()
    redis_service = compose["services"]["redis"]
    command = redis_service.get("command", "")
    assert "--requirepass" in str(command), (
        "redis-service in docker-compose.single-tenant.yml heeft geen --requirepass -- "
        "volledig onbeveiligde, poort-open Redis (SEC-ARCH-002, erger dan origineel "
        "gerapporteerd: zelfs geen zwakke fallback zoals de base docker-compose.yml)"
    )
