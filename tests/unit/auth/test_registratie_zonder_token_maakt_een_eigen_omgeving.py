"""Unit-grenzen rond de voordeur (SP-KLANT-01 dag 1): geen tenant uit het verzoek, een limiet,
rollen altijd gezaaid, en een gelijke standaard voor `ENVIRONMENT`.

De GEDRAGSMETING over de echte app staat in `tests/integration/security/`:
`test_self_registration_creates_an_isolated_tenant.py`,
`test_self_registration_in_single_tenant_mode.py` en `test_startup_seeds_roles_and_templates.py`.
Dit bestand bewaakt wat zonder database te meten is. Het toetst STRUCTUUR (AST), geen tekst:
een toelichting die een naam noemt telt niet mee, en een stringconstante in een docstring ook niet.

**Autouse-fixtures die hier meetellen:** `tests/conftest.py` heeft `enforce_testing_env`,
`_reset_global_state` en een sessiefixture voor de eventloop; geen van de drie raakt de
`ENVIRONMENT`-variabele van `app_lifespan`, de AST van de routers of `db_manager`. De tests
patchen die laatste zelf, met `patch.object` en herstel.

**Mutatiebewijs** (op een KOPIE van de boom, zie het rapport; productiecode in de repo is niet
aangeraakt). Een regel per bewaakt element:
- `ENVIRONMENT`-default in `app_lifespan.py` ongelijk aan die in `main.py` ->
  `test_both_entry_points_default_to_the_same_environment` ROOD; gelijk -> GROEN
- de development-overslag in `_seed_default_roles` laten staan ->
  `test_roles_are_seeded_for_every_tenant_in_development` ROOD
- de overslag ook voor `production` toevoegen -> `..._in_production` ROOD
- `request.headers` of `request.query_params` lezen in `register_user` ->
  `test_the_registration_handler_reads_no_tenant_from_the_request` ROOD
- `@auth_limiter.limit` van `register_user` halen ->
  `test_the_registration_handler_is_rate_limited` ROOD
- een veld `tenant_id` in `RegistrationRequest` ->
  `test_the_public_schema_has_no_tenant_or_privilege_field` ROOD
"""

from __future__ import annotations

import ast
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_ROUTER = Path("src/core/api/auth/router_registration.py")
_LIFESPAN = Path("src/core/app_lifespan.py")
_MAIN = Path("src/main.py")

#: Sterk genoeg voor de wachtwoordregels van het publieke schema.
_GELDIG = "Geldig" + "Wachtwoord1"


def _boom(pad: Path) -> ast.Module:
    return ast.parse(pad.read_text(encoding="utf-8"))


def _omgevingsdefault(pad: Path) -> str:
    """De default van `ENVIRONMENT = os.getenv("ENVIRONMENT", <default>)[.lower()]`.

    Via de AST: de aanroep wordt gezocht in de TOEWIJZING op moduleniveau, dus een
    toelichting of docstring die dezelfde regel citeert doet niet mee.
    """
    for knoop in _boom(pad).body:
        if not isinstance(knoop, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "ENVIRONMENT" for t in knoop.targets):
            continue
        for aanroep in ast.walk(knoop.value):
            if (
                isinstance(aanroep, ast.Call)
                and isinstance(aanroep.func, ast.Attribute)
                and aanroep.func.attr == "getenv"
                and len(aanroep.args) == 2
                and isinstance(aanroep.args[1], ast.Constant)
            ):
                return str(aanroep.args[1].value).lower()
    raise AssertionError(f"{pad}: geen `ENVIRONMENT = os.getenv(naam, default)` op moduleniveau")


def test_both_entry_points_default_to_the_same_environment() -> None:
    """`app_lifespan.py` stond op `development`, `main.py` op `production`: dezelfde start gaf
    twee omgevingen, en het zaaien van rollen hing aan de verkeerde."""
    assert _omgevingsdefault(_LIFESPAN) == _omgevingsdefault(_MAIN)


def _registratiefunctie() -> ast.AsyncFunctionDef:
    for knoop in ast.walk(_boom(_ROUTER)):
        if isinstance(knoop, ast.AsyncFunctionDef) and knoop.name == "register_user":
            return knoop
    raise AssertionError("register_user bestaat niet meer in router_registration.py")


def _zonder_docstring(functie: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
    kopie = ast.parse(ast.unparse(functie)).body[0]
    assert isinstance(kopie, ast.AsyncFunctionDef)
    if (
        kopie.body
        and isinstance(kopie.body[0], ast.Expr)
        and isinstance(kopie.body[0].value, ast.Constant)
        and isinstance(kopie.body[0].value.value, str)
    ):
        kopie.body = kopie.body[1:]
    return kopie


#: Wat uit het VERZOEK komt. `request.client.host` (het IP voor de logregel) is toegestaan.
_VERZOEKBRONNEN = {"headers", "query_params", "path_params", "cookies"}


def test_the_registration_handler_reads_no_tenant_from_the_request() -> None:
    functie = _zonder_docstring(_registratiefunctie())

    gelezen = {
        k.attr
        for k in ast.walk(functie)
        if isinstance(k, ast.Attribute)
        and isinstance(k.value, ast.Name)
        and k.value.id == "request"
        and k.attr in _VERZOEKBRONNEN
    }

    assert not gelezen, f"register_user leest {sorted(gelezen)} uit het verzoek (NOOIT-lijst)"


def test_the_registration_handler_may_still_read_the_client_address() -> None:
    """GROEN: de legitieme helft. 'Lees niets uit request' is anders een te grove regel; het
    IP-adres voor het auditspoor moet er nog steeds uit mogen."""
    functie = _zonder_docstring(_registratiefunctie())

    assert any(isinstance(k, ast.Attribute) and k.attr == "client" for k in ast.walk(functie)), (
        "register_user leest request.client niet meer; het auditspoor mist dan het IP"
    )


def test_the_registration_handler_is_rate_limited() -> None:
    """Een publiek pad dat tenants aanmaakt is een misbruikoppervlak (brief, Devil's Advocate)."""
    functie = _registratiefunctie()

    beperkt = [
        d
        for d in functie.decorator_list
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "limit"
    ]

    assert beperkt, "register_user heeft geen snelheidslimiet-decorator (`.limit(...)`)"


_VERBODEN_VELDEN = {
    "tenant_id",
    "tenant",
    "tenant_slug",
    "slug",
    "role",
    "role_id",
    "role_name",
    "roles",
    "is_superuser",
    "is_active",
}


def test_the_public_schema_has_no_tenant_or_privilege_field() -> None:
    """Een organisatienaam mag er komen (open vraag voor Rakesh), een tenant-sleutel of een
    privilegeveld niet: dan is de tenant of de rol uit het verzoek te kiezen."""
    from src.core.auth.auth_service import RegistrationRequest

    aanwezig = _VERBODEN_VELDEN & set(RegistrationRequest.model_fields)

    assert not aanwezig, f"RegistrationRequest draagt {sorted(aanwezig)}"


def test_the_public_schema_still_accepts_the_fields_the_form_sends() -> None:
    """GROEN: de legitieme helft. Het formulier stuurt naam, e-mail en wachtwoord (client.ts:367)."""
    from src.core.auth.auth_service import RegistrationRequest

    verzoek = RegistrationRequest(email="nieuw@example.com", password=_GELDIG, name="Nieuwe Klant")

    assert verzoek.email == "nieuw@example.com"


def _sessie_met_tenants(tenant_ids: list[int]) -> MagicMock:
    resultaat = MagicMock()
    resultaat.all.return_value = [(t,) for t in tenant_ids]
    sessie = MagicMock()
    sessie.execute = AsyncMock(return_value=resultaat)
    return sessie


async def _rol_zaailus_in(omgeving: str, tenant_ids: list[int]) -> AsyncMock:
    """Draai de ECHTE `_seed_default_roles`; de sessie en de RBAC-dienst zijn dubbels.

    Dit is een mock die toont DAT er voor elke tenant wordt gezaaid (behavior verification,
    bedoeld): de grens die telt is "wordt ensure_default_roles aangeroepen", niet de SQL. De
    echte SQL wordt in de integratietest gemeten.
    """
    from src.core import app_lifespan

    sessie = _sessie_met_tenants(tenant_ids)

    @asynccontextmanager
    async def nep_sessie():  # type: ignore[no-untyped-def]
        yield sessie

    @asynccontextmanager
    async def nep_adopt(_db, _tenant_id):  # type: ignore[no-untyped-def]
        yield

    rbac = MagicMock()
    rbac.ensure_default_roles = AsyncMock()

    with (
        patch.object(app_lifespan, "ENVIRONMENT", omgeving),
        patch.object(app_lifespan.db_manager, "get_session", nep_sessie),
        patch("src.core.services.rbac_service.RBACService", return_value=rbac),
        patch("src.core.database.bypass_session.adopt_tenant", nep_adopt),
        patch.object(app_lifespan, "_koppel_de_gezaaide_beheerder", AsyncMock()),
    ):
        await app_lifespan._seed_default_roles()

    return rbac.ensure_default_roles


@pytest.mark.asyncio
async def test_roles_are_seeded_for_every_tenant_in_development() -> None:
    zaaien = await _rol_zaailus_in("development", [5, 6])

    assert [c.args[0] for c in zaaien.await_args_list] == [5, 6]


@pytest.mark.asyncio
async def test_roles_are_seeded_for_every_tenant_in_production() -> None:
    """GROEN: de omgekeerde helft. Het zaaien zelf werkt al buiten development."""
    zaaien = await _rol_zaailus_in("production", [5, 6])

    assert [c.args[0] for c in zaaien.await_args_list] == [5, 6]
