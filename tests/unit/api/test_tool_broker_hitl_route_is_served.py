"""De HITL-goedkeuringsroute van de tool-broker moet door de app WORDEN GESERVEERD (ADR-036 OP-37).

**Waarom dit een eigen test verdient, en waarom het geen cosmetisch probleem is.** Gemeten
2026-08-05: er zijn TWEE gescheiden HITL-systemen met eigen tabellen.

- `hitl_requests` (`governance/models.py:291`) wordt gevuld door `als/enterprise/gatekeeper.py:561`
  en goedgekeurd door `/api/v1/gatekeeper/hitl/{approve,reject}` -- die route WORDT geserveerd. Dat
  is een gesloten lus.
- `hitl_tickets` (`tool_broker/models.py:29`) wordt gevuld door `copilot/service.py:528`, maar
  approve en reject staan in `src/core/tool_broker/router.py` (:647, :700) en die router had **nul
  importeurs**.

De poort in `tool_broker/service.py:227` leest via `hitl_store.get_approval_status()` juist die
TWEEDE tabel. Daarmee was de keten: een HIGH-risk actie via de copilot maakt een ticket, dat ticket
kan via de API nooit worden goedgekeurd, de actie blijft permanent geblokkeerd, en zijn onbewerkte
inhoud blijft eeuwig staan. ADR-015 was op dit pad fail-closed maar onbruikbaar -- een
veiligheidsfunctie die stil niets doet.

**Waarom dit lang onzichtbaar bleef.** `tests/architecture/test_frontend_backend_endpoint_contract.py`
toetst exact TWEE endpoints (twin profile, council decisions), terwijl `frontend/src/lib/api/hitl.ts`
er vier aanroept. Een contracttest met twee gevallen is een steekproef, geen contract.

**Voorwaarde die eerst vervuld moest zijn.** Deze route mounten mocht pas nadat approve, reject EN
pending een rolcheck hadden (`_require_approver`, commit `de74568c` / OP-56). Zonder die check zou
mounten het gat juist openzetten: elke ingelogde gebruiker had dan elk ticket kunnen goedkeuren, en
`/hitl/pending` levert het onbewerkte `tool_input` van elk openstaand ticket. Daarom staat OP-56
voor OP-37, en daarom toetst dit bestand BEIDE eigenschappen -- geserveerd EN geborgd.
"""

from __future__ import annotations

from typing import Any

import pytest

#: De VIER endpoints die samen de goedkeuringslus vormen -- precies de vier die
#: `frontend/src/lib/api/hitl.ts` aanroept. `pending` hoort erbij: zonder lijst kan een goedkeurder
#: niet zien wat er wacht, en de rolcheck erop is de reden dat de onbewerkte waarden daar mogen
#: staan (AI Act art. 14).
#:
#: `audit` stond hier eerst NIET in, terwijl de frontend hem wel aanroept -- gevonden door een
#: blinde review op 2026-08-06. Deze test diagnosticeert in zijn eigen docstring dat de
#: contract-guard tussen frontend en backend te smal is, en liet toen zelf een van de vier
#: aanroepen onbewaakt.
HITL_PATHS = (
    "/api/v1/tools/hitl/pending",
    "/api/v1/tools/hitl/approve",
    "/api/v1/tools/hitl/reject",
    "/api/v1/tools/hitl/audit",
)


def _routes_by_path() -> dict[str, Any]:
    """De routes van de GEASSEMBLEERDE app, niet van de leaf-router.

    Dit onderscheid is de hele bevinding: de leaf-router bestond en was getest, maar werd nergens
    geincludeerd. Een test op de leaf-router had dat niet kunnen zien.
    """
    from fastapi.routing import APIRoute

    from src.main import create_test_app

    app = create_test_app()
    return {route.path: route for route in app.routes if isinstance(route, APIRoute)}


def _dependency_names(route: Any) -> set[str]:
    """Alle dependency-functienamen van een route, recursief."""
    names: set[str] = set()

    def walk(dependant: Any) -> None:
        for sub in getattr(dependant, "dependencies", []):
            call = getattr(sub, "call", None)
            if call is not None:
                names.add(getattr(call, "__name__", ""))
            walk(sub)

    walk(route.dependant)
    return names


@pytest.mark.unit
@pytest.mark.parametrize("path", HITL_PATHS)
def test_the_hitl_route_is_served_by_the_app(path: str) -> None:
    routes = _routes_by_path()

    assert path in routes, (
        f"{path} bestaat niet in de geassembleerde app, terwijl `copilot/service.py:528` wel "
        "tickets aanmaakt in de tabel die deze route beheert en `tool_broker/service.py:227` die "
        "tabel leest voordat een HIGH-risk actie mag lopen. Zonder deze route kan zo'n actie nooit "
        "worden goedgekeurd: hij blijft permanent geblokkeerd en zijn onbewerkte inhoud blijft "
        "staan. Mount de router via een registry-entry in `src/core/api/registries/`."
    )


@pytest.mark.unit
@pytest.mark.parametrize("path", HITL_PATHS)
def test_the_served_route_requires_authentication(path: str) -> None:
    """Vangnet: geserveerd EN geborgd, niet het een zonder het ander.

    Zonder deze assertie zou "de router mounten" de eerste test groen maken terwijl het gat juist
    wijder wordt -- dat is precies de reden dat OP-56 voor OP-37 ging.
    """
    routes = _routes_by_path()
    if path not in routes:
        pytest.skip("route wordt nog niet geserveerd -- zie de test hierboven")

    names = _dependency_names(routes[path])
    assert any("current_user" in name for name in names), (
        f"{path} heeft geen authenticatie-dependency; gevonden: {sorted(names)}. Zonder "
        "geauthenticeerde gebruiker kan `_require_approver` niets toetsen en is de rolcheck een "
        "no-op."
    )
