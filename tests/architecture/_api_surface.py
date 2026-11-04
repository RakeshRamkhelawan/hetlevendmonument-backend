"""Gedeelde meting van het API-oppervlak: welke routes zijn er, en welke hebben auth?

**Waarom dit een gedeelde module is (ADR-036 OP-62/OP-73).** Het register noteert "839 routes,
155 zonder auth-dependency" als een MOMENTOPNAME uit een handmatige meting. Zo'n getal is niet
te controleren en veroudert stil: bij de hermeting van 2026-08-29 kon het niet worden
gereproduceerd, omdat de meting een geassembleerde FastAPI-app vereist. Een statische AST-telling
gaf een heel ander getal (997 gedeclareerd / 290 zonder), en die twee meten niet hetzelfde --
gedeclareerd is niet hetzelfde als geserveerd.

Deze module meet op de ECHTE app, dezelfde die `create_test_app()` bouwt, zodat het getal
reproduceerbaar is in plaats van overgeleverd. Twee guards gebruiken hem: de routetelling
(OP-62) en de frontend/backend-contracttoets (OP-73). Een tweede meting die een ander antwoord
geeft is de faalvorm waar deze reeks vol mee zit.

Bestand begint met een underscore: pytest verzamelt hem dan niet als testmodule.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

#: Namen (of naamdelen) die een dependency als authenticatie/autorisatie herkennen. Bewust
#: RUIM: een vals-positief maakt de guard te mild op een enkele route, een vals-negatief maakt
#: het getal onbruikbaar doordat halve applicatie plotseling "zonder auth" heet.
_AUTH_MERKERS = (
    "get_current_user",
    "get_current_tenant_id",
    "get_current_active_user",
    "get_current_admin",
    "current_active_user",
    "require_",
    "verify_",
    "authenticate",
    "oauth2",
    "api_key",
    "admin_required",
)


def _dependency_namen(dependant: Any, gezien: set[int] | None = None) -> set[str]:
    """Alle callable-namen in de dependency-boom van een route, recursief."""
    if gezien is None:
        gezien = set()
    namen: set[str] = set()
    call = getattr(dependant, "call", None)
    if call is not None:
        namen.add(getattr(call, "__name__", str(call)))
    for sub in getattr(dependant, "dependencies", None) or []:
        if id(sub) in gezien:
            continue
        gezien.add(id(sub))
        namen |= _dependency_namen(sub, gezien)
    return namen


def _heeft_auth(namen: set[str]) -> bool:
    kleine = {n.lower() for n in namen}
    return any(merker in naam for naam in kleine for merker in _AUTH_MERKERS)


@lru_cache(maxsize=1)
def _app() -> Any:
    # `create_app(testing=True)` slaat `register_all_routers()` over (src/main.py:141); alleen
    # `create_test_app()` registreert alles. Zonder dat verschil meet de guard een lege app.
    from src.main import create_test_app

    return create_test_app()


@lru_cache(maxsize=1)
def routes_met_auth_status() -> tuple[tuple[str, str, bool], ...]:
    """Per route: (pad, methoden, heeft een auth-dependency)."""
    resultaat: list[tuple[str, str, bool]] = []
    for route in _app().routes:
        dependant = getattr(route, "dependant", None)
        pad = getattr(route, "path", None)
        if dependant is None or pad is None:
            continue
        methoden = ",".join(sorted(getattr(route, "methods", None) or []))
        resultaat.append((pad, methoden, _heeft_auth(_dependency_namen(dependant))))
    return tuple(resultaat)


def route_paden() -> set[str]:
    """Alle geserveerde paden. Ook routes zonder dependant (statisch, docs) tellen mee."""
    return {
        getattr(route, "path")
        for route in _app().routes
        if getattr(route, "path", None) is not None
    }


def paden_zonder_auth() -> list[str]:
    return sorted({pad for pad, _methoden, auth in routes_met_auth_status() if not auth})


def pad_heeft_backend_match(api_pad: str, routes: set[str]) -> bool:
    """Matcht een frontend-pad op een geserveerde route?

    Overgenomen uit `test_frontend_backend_endpoint_contract.py` zodat er EEN definitie is.
    Beide kanten worden van een leidende `/api` of `/api/v1` ontdaan: sommige routers
    registreren zonder dat voorvoegsel en krijgen het via `include_router(prefix=...)`, de
    meeste declareren het zelf. Zonder ook de route te strippen matcht een self-prefixed route
    nooit.
    """
    genormaliseerd = re.sub(r"^/api(/v1)?", "", api_pad)
    patroon = re.sub(r"\{[^}]+\}", r"[^/]+", genormaliseerd)
    for route in routes:
        route_gestript = re.sub(r"^/api(/v1)?", "", route)
        route_patroon = re.sub(r"\{[^}]+\}", r"[^/]+", route_gestript)
        if re.fullmatch(patroon, route_patroon) or re.fullmatch(patroon, route):
            return True
    return False
