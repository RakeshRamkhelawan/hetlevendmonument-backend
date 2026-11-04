"""`api/v1/tenant_management/` mag in de echte app niet bereikbaar zijn (Gate 2, 2026-10-19).

**Waarom.** Die map heeft een eigen `TenantCreate`/`TenantUpdate` met een los `settings`-veld en een
`update_tenant` die `settings` als geheel vervangt (`setattr`). Zonder de controle en het behoud van de
taalmodelkeuze (`src/core/shared/tenant_llm_keuze.py`, ADR-041 B14) zou een PUT met `settings={}` de keuze
`ollama` van een klant wissen, waarna die stil op Mistral (gehuurd) stond. De live tenantroutes lopen via
`api/v1/tenants/` en `TenantService`, die de keuze wel valideren en behouden.

**Gemeten (2026-10-19, `create_test_app()`, 930 routes):** nul routes uit `tenant_management`; de
tenant-PUT wordt bediend door `src.core.api.v1.tenants.tenants_detail_router`. De map is dode code
(ADR-036 OP-224). Deze guard faalt zodra dat verandert: wie hem ooit aansluit, moet eerst dezelfde
keuzecontrole en `behoud_llm_keuze` overnemen (of de schema's van `tenants` hergebruiken).

**Uitgebreid 2026-10-22 (nazorg debiteuren).** `update_tenant` van de LIVE route neemt nu ook de instellingen met een eigen
route (vier ogen, de escalatietermijn) altijd uit de oude waarde (`src/core/shared/tenant_instellingen.py`,
`ALLEEN_EIGEN_ROUTE`). `crud_router.update_tenant` van deze map leest zonder slot en vervangt `settings` geheel: een
beheerder zet daarmee vier ogen UIT langs de eigen route met zijn controles en auditregel heen. Gemeten 2026-10-22: 0 van
938 routes uit deze map zijn gemonteerd.

**Mutatiebewijs:** het aansluiten van `tenant_management.router` in `api/registries/tenants.py` maakt deze test
ROOD; zonder die regel is hij GROEN.
"""

from __future__ import annotations

_VERBODEN = "src.core.api.v1.tenant_management"


def test_geen_enkele_route_van_de_echte_app_komt_uit_tenant_management() -> None:
    from src.main import create_test_app

    app = create_test_app()

    uit_tenant_management = sorted(
        f"{sorted(getattr(route, 'methods', None) or [])} {getattr(route, 'path', '?')}"
        for route in app.routes
        if getattr(getattr(route, "endpoint", None), "__module__", "").startswith(_VERBODEN)
    )

    assert uit_tenant_management == [], (
        "api/v1/tenant_management is bereikbaar geworden: zijn eigen TenantUpdate zet `settings` zonder "
        "keuzecontrole en zonder behoud van `llm_provider` (ADR-041 B14), en laat vier ogen en de "
        "escalatietermijn wissen. Neem eerst `_valideer_llm_keuze` en `behoud_beheerde_instellingen` "
        "(`shared/tenant_instellingen.py`) over, of gebruik de `tenants`-schema's. "
        f"Bereikbaar: {uit_tenant_management[:5]}"
    )


def test_controlegroep_de_live_tenantroutes_zijn_wel_aangesloten() -> None:
    """Zonder deze test is de guard hierboven hol: een app zonder tenantroutes slaagt er ook voor.

    Regie, 2026-10-19 (punt 1b): de eerste test telt routes uit `tenant_management`; was `create_test_app()`
    leeg of werd de moduleprefix hernoemd, dan bleef hij groen zonder iets te bewaken. De live
    tenantroutes (`src.core.api.v1.tenants`) MOETEN er wel in staan.
    """
    from src.main import create_test_app

    app = create_test_app()

    uit_tenants = [
        getattr(route, "path", "?")
        for route in app.routes
        if getattr(getattr(route, "endpoint", None), "__module__", "").startswith(
            "src.core.api.v1.tenants"
        )
    ]

    assert uit_tenants != [], (
        "geen enkele route uit src.core.api.v1.tenants gevonden: de guard op tenant_management ziet "
        "dan niets meer en is hol"
    )
