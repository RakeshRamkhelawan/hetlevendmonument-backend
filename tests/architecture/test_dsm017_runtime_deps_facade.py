"""DSM-017 Dag 3: auth/runtime_deps.py facade voor agent_runtime laag.

Rode tests geschreven VOOR de fix (FA-002 procesafspraak).
Fix: src/core/auth/runtime_deps.py aanmaken + 7 copilot/services bestanden migreren.

Correctie tov plan: Ce-reductie is 1 edge (16->15), niet 7. audit_endpoints.py heeft
2 auth imports (de enige bestand in scope met meer dan 1). Architecturele waarde
(stable import point voor agent_runtime->auth) rechtvaardigt de facade.

**OP-204, 2026-09-04: plafond terug naar 16, gedateerd.** `src/core/agents/
ml_ethics_engine.py` had een BOM (zie OP-203) en importeert
`SecureModelLoader` uit `src.core.security.secure_pickle` -- geclassificeerd
als `auth` via `MODULE_MAP` (security is een auth-subdomein). Dat importregel
bestond al sinds de BOM binnenkwam (2026-06-03); hij was alleen onzichtbaar
voor deze scanner. `audit_endpoints.py` blijft op zijn geconsolideerde 1 regel
staan (de SP-DSM-017-fix is niet teruggedraaid) -- het is een NIEUW bestand
dat de teller optilt, geen regressie op de oude fix. Verlagen kan alleen door
een ANDER, ongerelateerd bestand met 2+ losse auth-importregels samen te
voegen (bijv. `voice_routes.py`, 3 regels) -- dat is bewust niet gedaan in
deze wijziging (CLAUDE.md Surgical Changes: raak geen bestand aan dat niets
met deze BOM-opruiming te maken heeft).
"""

from pathlib import Path

import pytest

from scripts.dsm_full_analysis import SOURCE_DIRS, scan_module


@pytest.mark.architecture
def test_dsm017_runtime_deps_facade_exists() -> None:
    """src/core/auth/runtime_deps.py moet bestaan na SP-DSM-017 dag 3.

    Facade biedt agent_runtime laag (copilot, services) een stable import point
    voor auth-primitives (UserResponse, get_current_user, WebSocketAuthenticator, etc.).
    """
    assert Path("src/core/auth/runtime_deps.py").exists(), (
        "src/core/auth/runtime_deps.py ontbreekt. "
        "Aanmaken als re-export facade voor agent_runtime->auth consumers."
    )


#: Gemeten 2026-09-04 (OP-204): plafond gedateerd omhoog van 15 naar 16. Reden per regel
#: zodat een volgende lezer weet WELK bestand de ruimte gebruikt en waarom.
_CEILING_REASON = (
    "src/core/agents/ml_ethics_engine.py had een BOM (OP-203); zonder BOM importeert het "
    "SecureModelLoader uit src.core.security.secure_pickle, geclassificeerd als 'auth' -- "
    "OP-204, Fase D, 2026-09-04. "
    "PLUS 2026-09-23 (BE-LLM-004, 15 -> 17, gemeten tegen origin/develop 0a69e1ab): "
    "tenant_llm_provider_service.bouw_tenant_llm_service() haalt "
    "src.core.security.llm_endpoint_policy en src.core.security.tenant_secret_encryption "
    "binnen. Beide zijn onvermijdelijk zodra een agent het taalmodel van zijn EIGEN klant "
    "gebruikt: de opgeslagen sleutel moet ontsleuteld en het opgeslagen adres opnieuw "
    "gecontroleerd worden. Verstoppen achter importlib was mogelijk en is bewust NIET gedaan "
    "-- dat verlaagt de meter zonder de afhankelijkheid te verlagen"
)
AGENT_RUNTIME_AUTH_CEILING = 17


@pytest.mark.architecture
def test_dsm017_agent_runtime_auth_at_most_15() -> None:
    """agent_runtime->auth <= 16 (OP-204-plafond, zie _CEILING_REASON hierboven).

    Baseline SP-DSM-017 dag 3: 15 (na consolidatie audit_endpoints.py 2->1 edge).
    OP-204 tilde dit op naar 16 -- geen regressie op die fix, een ander bestand
    (ml_ethics_engine.py) werd door de BOM-opruiming pas zichtbaar.
    """
    counts, _, _ = scan_module("agent_runtime", SOURCE_DIRS.get("agent_runtime", []))
    auth_edges = counts.get("auth", 0)
    assert auth_edges <= AGENT_RUNTIME_AUTH_CEILING, (
        f"agent_runtime->auth = {auth_edges} (verwacht <= {AGENT_RUNTIME_AUTH_CEILING}). "
        f"{_CEILING_REASON}"
    )


@pytest.mark.architecture
def test_dsm017_agent_runtime_auth_trending_down() -> None:
    """Signaleert (blokkeert niet) zodra het plafond weer verlaagd kan worden.

    Zelfde stramien als test_api_layer_violations_trending_down in
    tests/architecture/test_dsm_api_violations.py.
    """
    counts, _, _ = scan_module("agent_runtime", SOURCE_DIRS.get("agent_runtime", []))
    auth_edges = counts.get("auth", 0)
    if auth_edges < AGENT_RUNTIME_AUTH_CEILING:
        pytest.xfail(
            f"agent_runtime->auth daalde naar {auth_edges}; verlaag "
            f"AGENT_RUNTIME_AUTH_CEILING in {Path(__file__).name}"
        )
