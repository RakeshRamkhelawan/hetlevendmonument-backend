"""DSM-018 Dag 1: auth/api_deps.py facade voor core_api laag.

Rode tests geschreven VOOR de fix (FA-002 procesafspraak).
Fix: src/core/auth/api_deps.py aanmaken + 30 core_api bestanden migreren (Batch A).

Doel: core_api Ce_excl_shared 966 -> <=800 (Grade A+) in 4 dagen.
Dag 1: facade aanmaken + Batch A top-30 bestanden op auth-import-telling.
"""

from pathlib import Path

import pytest

from scripts.dsm_full_analysis import SOURCE_DIRS, scan_module

_REPO_ROOT = Path(__file__).parents[2]


@pytest.mark.architecture
def test_dsm018_api_deps_facade_exists() -> None:
    """src/core/auth/api_deps.py moet bestaan na SP-DSM-018 Dag 1.

    Facade biedt core_api laag (routers, endpoints) een stable import point
    voor auth-primitives. Na migratie heeft elk bestand 1 auth-import in
    plaats van 2-5 losse imports.
    """
    facade = _REPO_ROOT / "src" / "core" / "auth" / "api_deps.py"
    assert facade.exists(), (
        "src/core/auth/api_deps.py ontbreekt. "
        "Aanmaken als re-export facade voor core_api->auth consumers. "
        "SP-DSM-018 Dag 1."
    )


@pytest.mark.architecture
def test_dsm018_core_api_auth_ce_at_most_400() -> None:
    """core_api->auth Ce <= 400 na SP-DSM-018 Dag 1 Batch A migratie.

    Baseline 2026-06-26: core_api->auth ~450 edges (362 import-regels in src/core/api/).
    Na Batch A (top-30 bestanden): elke bestand gaat van 3-5 auth-imports naar 1.
    Verwachte reductie: ~60-80 edges. Ceiling 400 = baseline minus buffer.
    """
    counts, _, _ = scan_module("core_api", SOURCE_DIRS.get("core_api", []))
    auth_edges = counts.get("auth", 0)
    assert auth_edges <= 400, (
        f"core_api->auth = {auth_edges} (verwacht <= 400 na SP-DSM-018 Dag 1 Batch A). "
        "Fix: top-30 bestanden migreren van losse auth-imports naar api_deps facade. "
        "SP-DSM-018 Dag 1."
    )
