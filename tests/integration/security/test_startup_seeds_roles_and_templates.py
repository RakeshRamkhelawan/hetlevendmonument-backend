"""Opstarten zaait de standaardrollen (ook in `development`) en de platformsjablonen.

Twee gaten uit de brief ("Wat de verkenner mat"), beide gemeten op 549f385b:

1. `app_lifespan._seed_default_roles` slaat het zaaien over in modus `development`. Een
   beheerder krijgt dan nul rollen, een token met alleen `users:read`, en overal 403. Besluit:
   rollen worden ALTIJD gezaaid, idempotent, ongeacht `ENVIRONMENT`.
2. `seed_platform_templates` heeft geen aanroeper in `src/`: de onboarding toont 0 sjablonen.
   Besluit: zaaien bij opstarten, idempotent.

**De tweede meting draait de ECHTE lifespan** (`app_lifespan(app)`), niet een benoemde hulp-
functie: de bouwer kiest de naam en de plek van het zaaien, het gedrag "na opstarten zijn er
sjablonen" is wat telt. Dat kost ~40 s per opstart (de lifespan wacht op Redis, dat lokaal
niet draait: gemeten 4 s per poging, drie keer). `seed.DEFAULT_ADMIN_PASSWORD` wordt met een testwaarde gepatcht
die de bestaande zaaier eist; er is geen taalmodelsleutel nodig of gebruikt.

**Wat de lifespan sloopt, en hoe dat hier wordt hersteld.** De shutdown roept
`close_database()` aan, dat `db_manager._initialized` op False zet. De sessie-fixture
`setup_db_manager` zet de engine maar een keer per testsessie, dus zonder herstel zouden
latere tests in dezelfde sessie falen. Het `finally` hieronder zet de vlag terug.

**Tijd/omgeving.** `ENVIRONMENT` staat onder pytest op `test` (tests/conftest.py); de dev-test
zet de modulevariabele zelf op `development` met `monkeypatch`.

Database als eigenaar `postgres`, dus zonder RLS; de meting onder de applicatierol hoort bij
OP-151. Het zaaien van sjablonen gebruikt `TenantFilterBypass` (brief: open punt onder OP-151).

**ROOD vandaag:** `test_default_roles_are_seeded_in_development_mode`,
`test_after_startup_the_template_list_is_not_empty`.
**GROEN, en dat is de bedoeling:** `test_default_roles_are_seeded_in_production_mode` (de
omgekeerde helft: het zaaien zelf blijft werken) en
`test_seeding_roles_twice_leaves_one_set_of_roles` (idempotent).

**Mutatiebewijs** (wegwerp-referentie-implementatie in een KOPIE, zie het rapport):
- development-overslag laten staan -> `..._in_development_mode` ROOD
- zaaien alleen in development weglaten (omgekeerd) -> `..._in_production_mode` ROOD
- niet idempotent (rollen dubbel) -> `test_seeding_roles_twice_*` ROOD
- sjablonen niet zaaien bij opstarten -> `test_after_startup_the_template_list_*` ROOD
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.auth.jwt_handler import jwt_handler
from tests.integration.security._voordeur_hulp import (  # noqa: F401  (fixtures)
    bearer,
    een_waarde,
    limiters_leeg,
    maak_app,
    rolnamen_van_tenant,
    voer_uit,
)

pytestmark = [pytest.mark.integration, pytest.mark.security]


def _tenant_zonder_rollen() -> int:
    slug = f"zonder-rollen-{uuid.uuid4().hex[:8]}"
    voer_uit(
        "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb) "
        "VALUES (:n, :s, true, 10, 50, 5)",
        n=slug,
        s=slug,
    )
    tenant_id = int(een_waarde("SELECT id FROM tenants WHERE slug = :s", s=slug))
    assert rolnamen_van_tenant(tenant_id) == set(), "de opstelling hoort een lege tenant te geven"
    return tenant_id


async def _zaai_rollen_zoals_bij_opstarten(omgeving: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core import app_lifespan

    monkeypatch.setattr(app_lifespan, "ENVIRONMENT", omgeving)
    await app_lifespan._seed_default_roles()


async def test_default_roles_are_seeded_in_development_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = _tenant_zonder_rollen()

    await _zaai_rollen_zoals_bij_opstarten("development", monkeypatch)

    assert {"admin", "user"} <= rolnamen_van_tenant(tenant_id)


async def test_default_roles_are_seeded_in_production_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GROEN: de omgekeerde helft. Het zaaien zelf werkt; alleen de overslag moet weg."""
    tenant_id = _tenant_zonder_rollen()

    await _zaai_rollen_zoals_bij_opstarten("production", monkeypatch)

    assert {"admin", "user"} <= rolnamen_van_tenant(tenant_id)


async def test_seeding_roles_twice_leaves_one_set_of_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GROEN: idempotent. Elke herstart zaait opnieuw; dubbele rollen zouden de unieke
    sleutel (tenant_id, name) breken of de rechten verdubbelen."""
    tenant_id = _tenant_zonder_rollen()
    await _zaai_rollen_zoals_bij_opstarten("production", monkeypatch)
    eerste = int(een_waarde("SELECT count(*) FROM roles WHERE tenant_id = :t", t=tenant_id))

    await _zaai_rollen_zoals_bij_opstarten("production", monkeypatch)

    tweede = int(een_waarde("SELECT count(*) FROM roles WHERE tenant_id = :t", t=tenant_id))
    assert (eerste, tweede) == (tweede, tweede) and tweede > 0


async def test_after_startup_the_template_list_is_not_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.app_lifespan import app_lifespan
    from src.core.database.database import db_manager

    from src.core.database import seed

    # Een MODULECONSTANTE (`seed.py:26`), gelezen bij het importeren: de omgevingsvariabele
    # zetten helpt dus niet meer, het attribuut patchen wel.
    monkeypatch.setattr(seed, "DEFAULT_ADMIN_PASSWORD", "Probe-Wachtwoord-123456")  # nosec B105
    assert een_waarde("SELECT count(*) FROM company_templates") == 0, "beginstand is niet leeg"
    admin = jwt_handler.create_access_token(
        data={
            "sub": "1",
            "user_id": 1,
            "email": "admin@integration.test",
            "tenant_id": 1,
            "scopes": ["admin:*"],
        }
    )
    app = maak_app()

    try:
        async with app_lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.get("/api/v1/templates", headers=bearer(admin))
    finally:
        db_manager._initialized = True  # lifespan-shutdown zet hem uit, zie docstring

    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    assert r.json()["total"] > 0, r.text[:300]
