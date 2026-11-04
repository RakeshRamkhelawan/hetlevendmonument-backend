"""Elke `/admin`-route heeft een rolcontrole in de route zelf.

Waarom (sprint-dag debiteuren Keten B, dag 5): de securitymiddleware wordt voor `/admin`-paden
versoepeld tot "alleen authenticatie". Vanaf dat moment hangt de beveiliging van elke
`/admin`-route af van de rolcontrole IN de route. Deze guard bewaakt dat.

Gemeten op de ECHTE app (`create_test_app()`, dezelfde als `_api_surface.py`;
`create_app(testing=True)` slaat `register_all_routers` over). Een route slaagt als:
  1. een dependency in de boom een `module::functie` uit ROL_DEPENDENCIES is, of
  2. de routefunctie zelf een echte `ast.Call` doet op require_admin / require_admin_role /
     is_admin (docstring verwijderd, geen duik in geneste functies), of
  3. de route in KNOWN_ZONDER_ROLCONTROLE staat (gedateerd, reden per regel).

Sleutel is `module::functie`, nooit alleen de naam: `require_admin` bestaat in meerdere
modules met een andere betekenis. De uitzonderingslijst is op het ENDPOINT gesleuteld
(`/admin/x` en `/api/v1/admin/x` delen een endpoint).

Mutatiebewijs (2026-10-07, met een kopie als terugweg):
  - `Depends(require_admin_role)` weggehaald uit `access_logs`
    (src/core/api/v1/admin/monitoring_router.py) -> test_elke_admin_route_heeft_een_rolcontrole
    ROOD; teruggezet -> groen.
  - de inline `await require_admin(admin_user)` weggehaald uit `toggle_feature`
    (src/core/api/v1/feature_flags/admin_router.py) -> ROOD; teruggezet -> groen.
  - een niet-bestaande sleutel in KNOWN_ZONDER_ROLCONTROLE -> test_uitzonderingslijst_is_niet_stale
    ROOD.
  - andere kant: de legitieme gevallen (dependency-route, inline-route, bewust publieke route)
    blijven in de ongemuteerde run groen; de herkenner-tests gebruiken synthetische functies.

Mutatiebewijs /system en /autonomous (2026-10-07, kopie als terugweg, geen git checkout):
  - `Depends(require_admin_user)` vervangen door `Depends(lambda: None)` in `llm_status`
    (src/core/api/v1/system/llm_status.py) -> test_elke_system_en_autonomous_route_heeft_een_rolcontrole
    ROOD (1 endpoint zonder rolcontrole); teruggezet -> 15 groen.
  - hetzelfde in `generate_code` (src/core/api/v1/autonomous/code_router.py) -> ROOD; teruggezet -> groen.
  - `_is_beheerroute` laten beslissen zonder het routesjabloon (altijd True na de voorfilter, dus
    `/api/v1/agents/system` telt als systeemroute) ->
    test_niveau_herkenner_onderscheidt_een_systeempad_van_een_gewoon_pad ROOD; teruggezet -> groen.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
import textwrap
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from fastapi.routing import APIRoute
from starlette.requests import Request

ROL_DEPENDENCIES: frozenset[str] = frozenset(
    {
        "src.core.api.v1.admin.dependencies::require_admin_role",
        # Strenger dan een tenantbeheerder: alleen een platformbeheerder (AP-verbinding per tenant,
        # brief 2026-10-21). Mutatiebewijs: Depends(require_platform_superuser) -> lambda: None in
        # ap_verbinding_router.py maakt beide guards hier ROOD.
        "src.core.api.v1.admin.dependencies::require_platform_superuser",
        "src.core.api.dependencies::require_admin_role",
        "src.core.api.dependencies::require_admin_user",
        "src.core.auth.dependencies::require_admin",
        "src.core.api.v1.foundation.dependencies::require_curator",
        "src.core.api.v1.foundation.dependencies::require_admin",
        # Strenger dan `require_admin_user`: alleen een PLATFORMbeheerder (`is_platform_superuser`). Voor de
        # providerwissel, die een gedeelde singleton van het platform omzet (BE-LLM-007, Gate 2 2026-10-20).
        "src.core.api.v1.system.dependencies::require_platform_beheerder",
    }
)

ROL_AANROEPEN: frozenset[str] = frozenset({"require_admin", "require_admin_role", "is_admin"})

KNOWN_ZONDER_ROLCONTROLE: dict[str, str] = {
    "src.core.api.v1.admin.monitoring_router::public_endpoint": (
        "bewust publiek (PublicEndpointRegistry), 2026-10-07"
    ),
}

MIN_ADMIN_ROUTES = 30

_Endpoint = tuple[Callable[..., Any], set[str], list[str]]


def _sleutel(call: Callable[..., Any]) -> str:
    return f"{call.__module__}::{call.__name__}"


def _dependency_sleutels(dependant: Any, gezien: set[int] | None = None) -> set[str]:
    if gezien is None:
        gezien = set()
    sleutels: set[str] = set()
    for sub in getattr(dependant, "dependencies", None) or []:
        if id(sub) in gezien:
            continue
        gezien.add(id(sub))
        call = getattr(sub, "call", None)
        if call is not None and hasattr(call, "__name__"):
            sleutels.add(_sleutel(call))
        sleutels |= _dependency_sleutels(sub, gezien)
    return sleutels


def _roept_rolcontrole_aan(knoop: ast.AST) -> bool:
    """Echte aanroep van een rolcontrole; duikt NIET in geneste functies of lambdas."""
    if isinstance(knoop, ast.Call):
        func = knoop.func
        naam = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if naam in ROL_AANROEPEN:
            return True
    for kind in ast.iter_child_nodes(knoop):
        if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if _roept_rolcontrole_aan(kind):
            return True
    return False


def doet_inline_rolcontrole(functie: Callable[..., Any]) -> bool:
    """True als de functie zelf een rolcontrole aanroept (docstring telt niet mee)."""
    boom = ast.parse(textwrap.dedent(inspect.getsource(functie)))
    definitie = boom.body[0]
    assert isinstance(definitie, (ast.FunctionDef, ast.AsyncFunctionDef))
    body = list(definitie.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return any(
        _roept_rolcontrole_aan(stap)
        for stap in body
        if not isinstance(stap, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


@lru_cache(maxsize=1)
def _admin_endpoints() -> dict[str, _Endpoint]:
    """endpoint-sleutel -> (functie, dependency-sleutels, paden)."""
    from src.main import create_test_app

    resultaat: dict[str, _Endpoint] = {}
    for route in create_test_app().routes:
        if not isinstance(route, APIRoute) or "/admin" not in route.path:
            continue
        sleutel = _sleutel(route.endpoint)
        deps = _dependency_sleutels(route.dependant)
        if sleutel in resultaat:
            resultaat[sleutel][2].append(route.path)
            resultaat[sleutel][1].update(deps)
        else:
            resultaat[sleutel] = (route.endpoint, deps, [route.path])
    return resultaat


def _soort(functie: Callable[..., Any], deps: set[str]) -> str:
    if deps & ROL_DEPENDENCIES:
        return "dependency"
    if doet_inline_rolcontrole(functie):
        return "inline"
    return "geen"


def test_er_worden_admin_routes_gevonden() -> None:
    """Vangnet: een lege enumeratie zou alle andere tests vacuous groen maken."""
    aantal_routes = sum(len(v[2]) for v in _admin_endpoints().values())
    assert aantal_routes >= MIN_ADMIN_ROUTES, f"slechts {aantal_routes} admin-routes gevonden"


def test_elke_admin_route_heeft_een_rolcontrole() -> None:
    zonder = sorted(
        f"{sleutel} ({', '.join(sorted(paden))})"
        for sleutel, (functie, deps, paden) in _admin_endpoints().items()
        if sleutel not in KNOWN_ZONDER_ROLCONTROLE and _soort(functie, deps) == "geen"
    )
    assert not zonder, (
        "Admin-routes zonder rolcontrole (geen Depends op een rolcontrole en geen inline "
        "require_admin/is_admin-aanroep): " + "; ".join(zonder)
    )


def test_uitzonderingslijst_is_niet_stale() -> None:
    """Een uitzondering die niet meer bestaat, of nu wel een rolcontrole heeft, moet eruit."""
    endpoints = _admin_endpoints()
    bestaat_niet = sorted(k for k in KNOWN_ZONDER_ROLCONTROLE if k not in endpoints)
    heeft_nu_controle = sorted(
        k
        for k in KNOWN_ZONDER_ROLCONTROLE
        if k in endpoints and _soort(endpoints[k][0], endpoints[k][1]) != "geen"
    )
    assert not bestaat_niet, f"uitzondering voor onbekende route: {bestaat_niet}"
    assert not heeft_nu_controle, f"uitzondering is niet meer nodig: {heeft_nu_controle}"


def test_rol_dependencies_wijzen_naar_bestaande_functies() -> None:
    """Een verzonnen sleutel in ROL_DEPENDENCIES zou stil niets bewaken."""
    kapot = [
        sleutel
        for sleutel in sorted(ROL_DEPENDENCIES)
        if not hasattr(importlib.import_module(sleutel.split("::")[0]), sleutel.split("::")[1])
    ]
    assert not kapot, f"ROL_DEPENDENCIES bevat onbestaande functies: {kapot}"


def test_herkenner_ziet_een_echte_aanroep() -> None:
    async def route(user: object) -> None:
        await require_admin(user)  # type: ignore[name-defined]  # noqa: F821

    assert doet_inline_rolcontrole(route) is True


def test_herkenner_negeert_naam_in_docstring() -> None:
    async def route(user: object) -> None:
        """Roept require_admin(user) en is_admin(user) NIET aan."""
        return None

    assert doet_inline_rolcontrole(route) is False


def test_herkenner_duikt_niet_in_geneste_functie() -> None:
    async def route(user: object) -> None:
        def nooit_aangeroepen() -> None:
            require_admin(user)  # type: ignore[name-defined]  # noqa: F821

    assert doet_inline_rolcontrole(route) is False


def test_de_dependency_herkenning_vindt_routes() -> None:
    """Vangnet op de herkenning zelf: er worden dependency-routes gevonden.

    Tot 2026-10-08 eiste dit ook minstens een inline-route. De laatste (`toggle_feature`) kreeg
    toen zijn rolcontrole als dependency (plan nazorg, punt d). De inline-herkenner wordt nog
    bewaakt door de drie synthetische `test_herkenner_*`-tests hierboven.
    """
    tel = {"dependency": 0, "inline": 0, "geen": 0}
    for functie, deps, _paden in _admin_endpoints().values():
        tel[_soort(functie, deps)] += 1
    assert tel["dependency"] > 0, tel


# --- Padparameters mogen het beveiligingsniveau niet bepalen (aed84fa0, dag 6) -------------
#
# De middleware herkent een admin-pad op de substring `/admin` in het VERZOEKPAD. Een route
# zonder `/admin` in het sjabloon wordt dan toch een admin-pad zodra een client de padparameter
# op `admin` zet. Daarom: per route met padparameters, het echte niveau voor een neutrale waarde
# gelijk aan het niveau voor `admin` en voor `adminx` (bevat `/admin` als prefix).
#
# Gemeten: op aed84fa0 (de `"/admin" in endpoint`-tak staat voor de /system- en
# /autonomous-takken) is test_padparameter_admin_verandert_het_beveiligingsniveau_niet ROOD;
# op cb1df6dd (tak ontbreekt) GROEN.

NEUTRALE_WAARDE = "x1"
ADMIN_ACHTIGE_WAARDEN = ("admin", "adminx")
MIN_ROUTES_MET_PADPARAMETER = 100

_PARAMETER = re.compile(r"\{[^}]+\}")


def vul_padparameters(sjabloon: str, waarde: str) -> str:
    """Vervang elke `{param}` of `{param:path}` door `waarde`."""
    return _PARAMETER.sub(waarde, sjabloon)


def _niveau_van(pad: str) -> str:
    """Het niveau dat de ECHTE middleware voor dit verzoekpad bepaalt."""
    from src.core.security.security_middleware import SecurityMiddleware

    async def _app(*_args: Any) -> None:
        return None

    middleware = SecurityMiddleware(_app, enable_security=True)  # type: ignore[arg-type]
    verzoek = Request({"type": "http", "method": "POST", "path": pad, "headers": []})
    return str(middleware._determine_security_level(pad, verzoek))


@lru_cache(maxsize=1)
def _routes_met_padparameter_zonder_admin() -> tuple[str, ...]:
    from src.main import create_test_app

    return tuple(
        sorted(
            {
                route.path
                for route in create_test_app().routes
                if isinstance(route, APIRoute) and "{" in route.path and "/admin" not in route.path
            }
        )
    )


#: Enige bewuste uitzondering (2026-10-07): `admin` als tenantSlug van de foundation-router is
#: een gereserveerd woord, door PublicEndpointRegistry opzettelijk fail-closed behandeld
#: (src/core/shared/public_registry.py, FOUNDATION_RESERVED_SLUGS). Zelfde gedrag op cb1df6dd.
#: het-levend-monument hangt de foundation-router onder `/api/v1`
#: (src/core/api/registries/foundation.py: `include_router(..., prefix="/api/v1")`);
#: upstream SanskritiSetu hangt hem op de wortel. Beide vormen zijn dezelfde router.
FOUNDATION_SLUG_PREFIXES = ("/{tenantSlug}/foundation/", "/api/v1/{tenantSlug}/foundation/")


def _is_gereserveerde_slug(sjabloon: str, waarde: str) -> bool:
    return waarde == "admin" and sjabloon.startswith(FOUNDATION_SLUG_PREFIXES)


def test_gereserveerde_slug_uitzondering_is_niet_stale() -> None:
    assert any(
        s.startswith(FOUNDATION_SLUG_PREFIXES) for s in _routes_met_padparameter_zonder_admin()
    ), "geen foundation-route met tenantSlug meer: haal FOUNDATION_SLUG_PREFIXES weg"


def test_er_worden_routes_met_padparameters_gevonden() -> None:
    """Vangnet: een lege enumeratie zou de test hieronder vacuous groen maken."""
    aantal = len(_routes_met_padparameter_zonder_admin())
    assert aantal >= MIN_ROUTES_MET_PADPARAMETER, f"slechts {aantal} routes met padparameter"


def test_padparameter_admin_verandert_het_beveiligingsniveau_niet() -> None:
    afwijkend = sorted(
        f"{sjabloon}: {waarde} -> {_niveau_van(vul_padparameters(sjabloon, waarde))} "
        f"i.p.v. {_niveau_van(vul_padparameters(sjabloon, NEUTRALE_WAARDE))}"
        for sjabloon in _routes_met_padparameter_zonder_admin()
        for waarde in ADMIN_ACHTIGE_WAARDEN
        if not _is_gereserveerde_slug(sjabloon, waarde)
        and _niveau_van(vul_padparameters(sjabloon, waarde))
        != _niveau_van(vul_padparameters(sjabloon, NEUTRALE_WAARDE))
    )
    assert not afwijkend, (
        "Een padparameter bepaalt het beveiligingsniveau (admin-herkenning op substring van het "
        "verzoekpad i.p.v. op de route): " + "; ".join(afwijkend)
    )


def test_vul_padparameters_vervangt_gewone_en_path_parameters() -> None:
    assert vul_padparameters("/a/{x}/b/{y:path}", "q") == "/a/q/b/q"


def test_niveau_herkenner_onderscheidt_een_systeempad_van_een_gewoon_pad() -> None:
    """Vangnet op `_niveau_van` zelf: het niveau hangt aan het ROUTESJABLOON, niet aan het pad.

    Gedrag BEWUST gewijzigd (Keten B nazorg, A): dit eiste dat `/api/v1/system/x1` een ander
    niveau kreeg dan `/api/v1/agents/x1` (ADMIN versus AUTHENTICATED). Beide zijn nu
    AUTHENTICATED; de beheerdersrol zit per route. Wat de herkenner nog moet kunnen is een
    sjabloon van een padparameter onderscheiden: `/system` als WAARDE van een padparameter op een
    gewone route (`/api/v1/agents/{id}`) is geen beheerroute. Bewaakt de herkenner zelf:
    een pad dat op een echt `/api/v1/system/`-sjabloon matcht wel, een parameterwaarde niet.
    """
    from starlette.requests import Request as _Request

    from src.core.security.security_middleware import SecurityMiddleware
    from src.main import create_test_app

    app = create_test_app()

    def beheer(pad: str) -> bool:
        verzoek = _Request(
            {"type": "http", "method": "GET", "path": pad, "headers": [], "app": app}
        )
        return SecurityMiddleware._is_beheerroute(pad, verzoek)

    assert beheer("/api/v1/system/llm-status") is True
    sjabloon = SecurityMiddleware._gematcht_routesjabloon(_Request({"type": "http", "method": "GET", "path": "/api/v1/agents/system", "headers": [], "app": app}))
    assert sjabloon is not None and "{" in sjabloon, sjabloon  # er IS een route met padparameter
    assert beheer("/api/v1/agents/system") is False
    assert beheer("/api/v1/agents/autonomous") is False
    assert beheer("/api/v1/system/bestaat-niet") is False  # 404: geen route, geen beheerroute


# --- /system en /autonomous: dezelfde plicht (Keten B nazorg, punt A) -----------------------
#
# De middleware weigert deze prefixen nu voor iedereen (ADMIN-niveau, claim wordt nooit gezet).
# De herstelroute is dezelfde als voor `/admin`: de middleware vraagt alleen authenticatie, de
# rolcontrole zit IN de route. Daarom moet elke `/api/v1/system/*`- en `/api/v1/autonomous/*`-route
# een rolcontrole hebben; deze test is ROOD tot de bouwer ze toevoegt (of een route bewust op
# KNOWN_SYSTEM_AUTONOMOUS_ZONDER_ROLCONTROLE zet, gedateerd en met reden).
# `require_scopes` telt NIET als rolcontrole: het is een RBAC-scope, geen beheerdersrol.

BEHEER_PREFIXEN = ("/api/v1/system/", "/api/v1/autonomous/")

KNOWN_SYSTEM_AUTONOMOUS_ZONDER_ROLCONTROLE: dict[str, str] = {}


@lru_cache(maxsize=1)
def _system_en_autonomous_endpoints() -> dict[str, _Endpoint]:
    from src.main import create_test_app

    resultaat: dict[str, _Endpoint] = {}
    for route in create_test_app().routes:
        if not isinstance(route, APIRoute) or not route.path.startswith(BEHEER_PREFIXEN):
            continue
        sleutel = _sleutel(route.endpoint)
        deps = _dependency_sleutels(route.dependant)
        if sleutel in resultaat:
            resultaat[sleutel][2].append(route.path)
            resultaat[sleutel][1].update(deps)
        else:
            resultaat[sleutel] = (route.endpoint, deps, [route.path])
    return resultaat


def test_er_worden_system_en_autonomous_routes_gevonden() -> None:
    """Vangnet: de brief noemt 9 + 14 sjablonen; een lege enumeratie maakt de test hieronder hol."""
    aantal = sum(len(v[2]) for v in _system_en_autonomous_endpoints().values())
    assert aantal >= 23, f"slechts {aantal} system/autonomous-routes gevonden"


def test_elke_system_en_autonomous_route_heeft_een_rolcontrole() -> None:
    zonder = sorted(
        f"{sleutel} ({', '.join(sorted(paden))})"
        for sleutel, (functie, deps, paden) in _system_en_autonomous_endpoints().items()
        if sleutel not in KNOWN_SYSTEM_AUTONOMOUS_ZONDER_ROLCONTROLE
        and _soort(functie, deps) == "geen"
    )
    assert not zonder, (
        f"{len(zonder)} system/autonomous-endpoints zonder rolcontrole: " + "; ".join(zonder)
    )


# --- Beheerroutes met een body: de rolcontrole staat in de dependencies (plan nazorg, punt d) --
#
# FastAPI valideert de body VOORDAT de handler draait. Een rolcontrole in de handler geeft een
# niet-beheerder dus 422 met de veldnamen en regels van het schema, in plaats van 403. Als
# dependency (op de decorator, de router of als parameter) komt de 403 eerst. Gemeten
# 2026-10-08 met fastapi 0.136.3, zie `tests/unit/security/test_rolcontrole_voor_de_body.py`.
#
# Kapotte JSON (geen geldige JSON) geeft WEL 422 voor de dependencies: FastAPI leest de body
# voordat hij dependencies oplost. Dat is een bewuste, geaccepteerde keuze -- het lekt alleen
# "dit is geen JSON", geen schema -- en vastgelegd in dezelfde unittest.
#
# Hier telt ALLEEN een dependency; een aanroep in de handler telt niet, want dat is precies het
# gat. Mutatiebewijs staat in de commit (2026-10-08).

BEHEER_BODY_PREFIXEN = (
    "/api/rbac/",
    "/api/admin/",
    "/admin/",
    "/api/v1/tenants",
    "/api/v1/users",
    "/api/gdpr/",
    "/api/v1/system/",
    "/api/v1/autonomous/",
    "/api/v1/domain-packs",
    "/api/v1/gatekeeper/hitl/",
)

#: Losse beheerroutes buiten de prefixen hierboven: (methode, pad).
BEHEER_BODY_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("PUT", "/api/v1/tools/hitl/four-eyes"),
        ("POST", "/execute"),
    }
)

#: Dependencies die een rol (of de tenantgrens van een beheeractie) toetsen. Elke nieuwe sleutel
#: wijst naar een functie die 403 geeft; `test_body_rol_dependencies_bestaan` bewaakt dat ze
#: bestaan.
BODY_ROL_DEPENDENCIES: frozenset[str] = ROL_DEPENDENCIES | frozenset(
    {
        "src.core.api.v1.rbac.dependencies::require_rbac_permission",
        "src.core.api.v1.tenant_management.dependencies::require_admin",
        "src.core.api.v1.user_management.dependencies::require_admin",
        "src.core.api.v1.tenants.dependencies::require_platform_superuser",
        "src.core.api.v1.tenants.dependencies::require_own_tenant_or_superuser",
        "src.core.api.v1.tenants.dependencies::require_tenant_beheerder",
        "src.core.api.v1.users.shared::require_user_manager",
        "src.core.api.domain_packs::require_domain_pack_admin",
        # Goedkeuren is een procesbevoegdheid (ADR-039, 2026-10-09): de poort voor de body vraagt
        # een goedkeurrecht uit role_permissions en niet langer een beheerdersrol.
        "src.core.api.v1.gatekeeper.gatekeeper_hitl_router::_require_an_approval_right",
    }
)

#: Beheerroutes met een body ZONDER rolcontrole-dependency, met de reden. Gesleuteld op
#: "METHODE pad".
KNOWN_BODY_ZONDER_ROL_DEPENDENCY: dict[str, str] = {
    "POST /api/rbac/permissions/check": (
        "2026-10-08 -- eigenaarschap: je eigen permissie mag iedereen controleren, die van een "
        "ander alleen met USER_MANAGE. Wie 'de ander' is staat in de body."
    ),
    "PUT /api/v1/users/me": "2026-10-08 -- eigen profiel, geen beheeractie",
    "PUT /api/v1/users/{user_id}": (
        "2026-10-08 -- eigenaarschap: een gebruiker mag zichzelf wijzigen; de tenant van de "
        "doelgebruiker is pas bekend na het laden"
    ),
    "PUT /api/v1/users/{user_id}/password": "2026-10-08 -- eigenaarschap: eigen wachtwoord",
    "POST /api/gdpr/export": "2026-10-08 -- inzagerecht van de gebruiker zelf (AVG art. 15/20)",
}


def _methoden(route: APIRoute) -> list[str]:
    return sorted(m for m in route.methods if m not in {"HEAD", "OPTIONS"})


@lru_cache(maxsize=1)
def _beheerroutes_met_body() -> dict[str, set[str]]:
    """'METHODE pad' -> dependency-sleutels, voor elke beheerroute met een body."""
    from src.main import create_test_app

    resultaat: dict[str, set[str]] = {}
    for route in create_test_app().routes:
        if not isinstance(route, APIRoute) or route.body_field is None:
            continue
        for methode in _methoden(route):
            if not (
                route.path.startswith(BEHEER_BODY_PREFIXEN)
                or (methode, route.path) in BEHEER_BODY_ROUTES
            ):
                continue
            sleutel = f"{methode} {route.path}"
            resultaat.setdefault(sleutel, set()).update(_dependency_sleutels(route.dependant))
    return resultaat


def test_er_worden_beheerroutes_met_een_body_gevonden() -> None:
    """Vangnet: de inventaris in het plan telde er ruim 30."""
    routes = _beheerroutes_met_body()
    assert len(routes) >= 30, f"slechts {len(routes)} beheerroutes met een body"
    for methode, pad in BEHEER_BODY_ROUTES:
        assert f"{methode} {pad}" in routes, f"losse beheerroute niet gevonden: {methode} {pad}"


def test_elke_beheerroute_met_een_body_heeft_de_rolcontrole_in_de_dependencies() -> None:
    zonder = sorted(
        sleutel
        for sleutel, deps in _beheerroutes_met_body().items()
        if sleutel not in KNOWN_BODY_ZONDER_ROL_DEPENDENCY and not deps & BODY_ROL_DEPENDENCIES
    )
    assert not zonder, (
        f"{len(zonder)} beheerroutes met een body controleren de rol pas in de handler (na de "
        "validatie van de body, dus 422 in plaats van 403): " + "; ".join(zonder)
    )


def test_body_uitzonderingslijst_is_niet_stale() -> None:
    routes = _beheerroutes_met_body()
    bestaat_niet = sorted(k for k in KNOWN_BODY_ZONDER_ROL_DEPENDENCY if k not in routes)
    heeft_nu_controle = sorted(
        k
        for k in KNOWN_BODY_ZONDER_ROL_DEPENDENCY
        if k in routes and routes[k] & BODY_ROL_DEPENDENCIES
    )
    assert not bestaat_niet, f"uitzondering voor onbekende route: {bestaat_niet}"
    assert not heeft_nu_controle, f"uitzondering is niet meer nodig: {heeft_nu_controle}"


def test_body_rol_dependencies_bestaan() -> None:
    """Een verzonnen sleutel zou stil niets bewaken. Fabrieken (rbac) tellen via hun naam."""
    kapot = [
        sleutel
        for sleutel in sorted(BODY_ROL_DEPENDENCIES)
        if not hasattr(importlib.import_module(sleutel.split("::")[0]), sleutel.split("::")[1])
    ]
    assert not kapot, f"BODY_ROL_DEPENDENCIES bevat onbestaande functies: {kapot}"
