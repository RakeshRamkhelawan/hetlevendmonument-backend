"""AUDIT-ARCH-2026-07-02 Groep 5 -- SEC-INFRA-001/003 (docker-compose.prod.yml).

Learning-worker en workflow-worker gebruikten een hardcoded 'postgres:postgres'
DATABASE_URL-fallback, en meerdere services gebruikten een REDIS_URL/
DRAMATIQ_BROKER_URL-fallback zonder credential terwijl de base docker-compose.yml
Redis wel met --requirepass beveiligt. In productie zijn deze env-vars altijd
gezet via Azure Container App secrets; een fallback met een zwak/ontbrekend
credential mag niet bestaan (fail-closed: ontbreken van de env-var moet de
container-start laten falen, niet stilzwijgend een onveilige default gebruiken).
"""

import re
from pathlib import Path

COMPOSE_FILE = Path("docker-compose.prod.yml").resolve()

FORBIDDEN_PATTERNS = [
    re.compile(r"postgres:postgres@"),
    re.compile(r"redis://redis:\d+/\d+\}"),  # REDIS_URL/-BROKER_URL fallback zonder credential
]


def test_no_hardcoded_postgres_credential_fallback() -> None:
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    matches = [line for line in content.splitlines() if "postgres:postgres@" in line]
    assert not matches, (
        "Hardcoded 'postgres:postgres'-credential-fallback gevonden in "
        f"docker-compose.prod.yml: {matches} (SEC-INFRA-001)"
    )


def test_no_credential_less_redis_url_fallback() -> None:
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    matches = [
        line
        for line in content.splitlines()
        if re.search(r"REDIS_URL:-redis://redis:\d+/\d+\}", line)
        or re.search(r"DRAMATIQ_BROKER_URL:-redis://redis:\d+/\d+\}", line)
    ]
    assert not matches, (
        "REDIS_URL/DRAMATIQ_BROKER_URL-fallback zonder credential gevonden in "
        f"docker-compose.prod.yml: {matches} (SEC-INFRA-003, inconsistent met "
        "Redis's --requirepass-eis in de base docker-compose.yml)"
    )
