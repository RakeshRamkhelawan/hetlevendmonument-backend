"""AUDIT-ARCH-2026-07-02 Groep 5 -- SEC-INFRA-002/003 (docker-compose.yml).

Base compose gebruikte ':-postgres' / ':-changeme_in_production' /
':-change-me-in-production' / ':-admin'-fallbacks voor credentials (Postgres-
wachtwoord, Redis-wachtwoord, ActivePieces-secrets, Grafana-admin-wachtwoord).
Vereiste vervanging: '${VAR:?<naam> is verplicht}' zodat een ontbrekende env-var
de opstart hard laat falen (fail-closed) i.p.v. een onveilige default te gebruiken.
"""

import re
from pathlib import Path

COMPOSE_FILE = Path("docker-compose.yml").resolve()

# credential-achtige env-var-namen die nooit een fallback-default mogen hebben
CREDENTIAL_VAR_PATTERN = re.compile(
    r"\$\{(?P<name>[A-Z_]*(?:PASSWORD|SECRET|KEY|TOKEN)[A-Z_]*):-[^}]+\}"
)


def test_no_credential_fallback_defaults_in_base_compose() -> None:
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    matches = CREDENTIAL_VAR_PATTERN.findall(content)
    assert not matches, (
        "Credential-env-vars met een ':-'-fallback-default gevonden in "
        f"docker-compose.yml: {sorted(set(matches))}. Vervang door "
        "'${VAR:?<naam> is verplicht}' (fail-closed, SEC-INFRA-002/003)."
    )


def test_no_literal_changeme_or_default_credential_strings() -> None:
    """POSTGRES_USER:-postgres blijft toegestaan (username is geen secret) -- alleen
    credential-waarden (wachtwoorden/secrets) mogen geen fail-open literal hebben."""
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    forbidden_literals = [
        "PASSWORD:-postgres}",
        ":-changeme_in_production}",
        ":-change-me-in-production}",
    ]
    violations = [literal for literal in forbidden_literals if literal in content]
    assert not violations, f"Verboden fail-open credential-fallback-literals gevonden: {violations}"
