"""Een rechtenwijziging is METEEN effectief -- in beide richtingen (ADR-036 OP-254).

WAAROM DEZE TEST BESTAAT
------------------------
Tot 2026-09-18 bewaarde `user_has_permission` elke autorisatiebeslissing een uur
(`config.redis_cache_ttl`, default 3600s), in Redis zodra `REDIS_URL` gezet was. Gemeten
via de echte servicemethodes, tegen een echte PostgreSQL:

    recht van een rol afnemen  -> `user_has_permission` bleef True geven
    rol aan een gebruiker geven -> bleef False geven

Dat is geen vertraging maar een verkeerd antwoord: het eerste geval is een ingetrokken
recht dat blijft werken. In Redis overleefde die beslissing elke replica en elke herstart
van de container, dus er was geen noodrem behalve handmatig ingrijpen.

De cache is verwijderd (zie de docstring van `RBACService` voor de vier metingen). Deze
test legt de uitkomst vast die dat moet opleveren.

WAAROM DIT EEN INTEGRATIETEST IS
--------------------------------
Het gaat om de samenhang tussen drie tabellen (`user_roles`, `roles`, `role_permissions`)
en de echte servicemethodes. Een unittest met testdubbels zou zijn eigen antwoord aan
beide kanten verzinnen en alleen bewijzen dat de functie deterministisch is. De
structurele tegenhanger die WEL zonder database draait, staat in
`tests/unit/rbac/test_de_permissiecontrole_heeft_geen_cache.py`.

Draaien:
    docker start sanskritisetu_test_db
    pytest tests/integration/security/test_een_rechtenwijziging_werkt_meteen.py

De verbinding komt van `tests.fixtures.testdatabase.testdatabase_url()`; wijs hier geen
eigen URL aan, ook niet in deze toelichting -- een poortscan nam op 2026-09-14 een vergeten
servicecontainer voor de testdatabase (OP-243), en
`tests/architecture/test_de_testdatabase_wordt_niet_geraden.py` bewaakt dat op TEKST.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.fixtures.testdatabase import testdatabase_url

#: Een resource en een rol die nergens anders bestaan, zodat deze test niets van een ander
#: pad raakt en zelf opruimt wat hij neerzet.
_PROEFRESOURCE = "op254_proefdomein"
_PROEFROL = "op254_proefrol"


@pytest.fixture
async def sessie() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(testdatabase_url())
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _leeg_de_proefstand(s: AsyncSession, gebruiker_id: int) -> None:
    await s.execute(text("DELETE FROM user_roles WHERE user_id = :u"), {"u": gebruiker_id})
    await s.execute(text("DELETE FROM role_permissions WHERE resource = :r"), {"r": _PROEFRESOURCE})
    await s.commit()


async def _verwijder_de_proefrol(s: AsyncSession) -> None:
    await s.execute(
        text(
            "DELETE FROM user_roles WHERE role_id IN "
            "(SELECT id FROM roles WHERE name = :n)"
        ),
        {"n": _PROEFROL},
    )
    await s.execute(
        text(
            "DELETE FROM role_permissions WHERE role_id IN "
            "(SELECT id FROM roles WHERE name = :n)"
        ),
        {"n": _PROEFROL},
    )
    await s.execute(text("DELETE FROM roles WHERE name = :n"), {"n": _PROEFROL})
    await s.commit()


async def _eerste_gebruiker_zonder_rollen(s: AsyncSession) -> tuple[int, int, int]:
    """(gebruiker_id, tenant_id, rol_id) -- de rol draagt een `*`/`*`-recht."""
    rij = (
        await s.execute(
            text(
                "SELECT u.id, u.tenant_id FROM users u "
                "WHERE u.tenant_id IS NOT NULL ORDER BY u.id OFFSET 1 LIMIT 1"
            )
        )
    ).first()
    if rij is None:
        pytest.skip("geen tweede gebruiker in de testdatabase om mee te proeven")
    gebruiker_id, tenant_id = int(rij[0]), int(rij[1])
    rol = (
        await s.execute(
            text(
                "SELECT r.id FROM roles r JOIN role_permissions p ON p.role_id = r.id "
                "WHERE r.tenant_id = :t AND p.resource = '*' AND p.action = '*' LIMIT 1"
            ),
            {"t": tenant_id},
        )
    ).scalar()
    if rol is None:
        pytest.skip("geen rol met een wildcardrecht in deze testdatabase")
    return gebruiker_id, tenant_id, int(rol)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_een_toegekende_rol_werkt_meteen(sessie: AsyncSession) -> None:
    from src.core.services.rbac_service import RBACService

    gebruiker_id, tenant_id, rol_id = await _eerste_gebruiker_zonder_rollen(sessie)
    await _leeg_de_proefstand(sessie, gebruiker_id)
    dienst = RBACService(sessie)
    rolnaam = (
        await sessie.execute(text("SELECT name FROM roles WHERE id = :r"), {"r": rol_id})
    ).scalar()
    assert isinstance(rolnaam, str), "rol zonder naam in de testdatabase"

    voor = await dienst.user_has_permission(gebruiker_id, "agents:read", tenant_id=tenant_id)
    assert voor is False, "de proefopstelling klopt niet: de gebruiker had al toegang"

    assert await dienst.assign_role(gebruiker_id, rolnaam, tenant_id) is True
    na = await dienst.user_has_permission(gebruiker_id, "agents:read", tenant_id=tenant_id)

    await _leeg_de_proefstand(sessie, gebruiker_id)
    assert na is True, (
        "Een toegekende rol werkt niet meteen door. Tot 2026-09-18 kwam dat door een "
        "permissiecache met een TTL van een uur die `assign_role` niet leegde (OP-254)."
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_een_afgenomen_recht_werkt_meteen(sessie: AsyncSession) -> None:
    """De veiligheidsrelevante richting: wat je afneemt, is meteen weg.

    **Let op de opzet, want de eerste versie van deze test mat niets.** Hij gebruikte een
    bestaande rol met een `*`/`*`-recht. Het afnemen van EEN specifiek recht verandert daar
    per definitie niets: de wildcard dekt het nog steeds, dus `True` bleef terecht `True`.
    De test faalde daardoor op een reden die niets met de cache te maken had. Daarom een
    EIGEN proefrol zonder wildcard, die deze test zelf aanmaakt en weer opruimt.
    """
    from src.core.services.rbac_service import RBACService

    gebruiker_id, tenant_id, _ = await _eerste_gebruiker_zonder_rollen(sessie)
    await _leeg_de_proefstand(sessie, gebruiker_id)
    await _verwijder_de_proefrol(sessie)

    rol_id = (
        await sessie.execute(
            text(
                "INSERT INTO roles (tenant_id, name, description, is_active) "
                "VALUES (:t, :n, 'tijdelijke proefrol OP-254', true) RETURNING id"
            ),
            {"t": tenant_id, "n": _PROEFROL},
        )
    ).scalar_one()
    await sessie.execute(
        text("INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r)"),
        {"u": gebruiker_id, "r": rol_id},
    )
    await sessie.execute(
        text(
            "INSERT INTO role_permissions (role_id, tenant_id, resource, action) "
            "VALUES (:r, :t, :res, 'read')"
        ),
        {"r": rol_id, "t": tenant_id, "res": _PROEFRESOURCE},
    )
    await sessie.commit()

    dienst = RBACService(sessie)
    voor = await dienst.user_has_permission(
        gebruiker_id, f"{_PROEFRESOURCE}:read", tenant_id=tenant_id
    )
    assert voor is True, "de proefopstelling klopt niet: het recht gold niet"

    # `tenant_id` gaat expliciet mee: sinds ADR-036 OP-256 controleert de dienst dat de
    # rol bij DEZE klant hoort, en zonder klantcontext (er is hier geen middleware)
    # weigert hij terecht met een RuntimeError.
    assert (
        await dienst.remove_permission_from_role(
            rol_id, _PROEFRESOURCE, "read", tenant_id=tenant_id
        )
        is True
    )
    na = await dienst.user_has_permission(
        gebruiker_id, f"{_PROEFRESOURCE}:read", tenant_id=tenant_id
    )

    await _leeg_de_proefstand(sessie, gebruiker_id)
    await _verwijder_de_proefrol(sessie)
    assert na is False, (
        "Een AFGENOMEN recht blijft werken. Dat is een actieve autorisatie-bypass: wie een "
        "te ruim recht terugneemt, denkt dat het weg is terwijl het dat niet is (OP-254)."
    )
