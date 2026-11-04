"""DSM-017 Dag 1: tenancy->agent_runtime backward dep gesloten.

Rode tests geschreven VOOR de fix (FA-002 procesafspraak, commit dea8d239).
Fix: agents.models -> shared in MODULE_MAP (scripts/dsm_full_analysis.py).

tenancy->governance (3 edges): vereist code-level verplaatsing van SecurityEvent naar shared
-- MODULE_MAP aanpak reduceert governance Ca waardoor I > 0.40. Tracked in
test_dsm_medium_pairs_tracking.py (ceiling <= 3). Fix in latere sprint dag.
"""

from pathlib import Path

import pytest


@pytest.mark.architecture
def test_dsm017_agents_models_classified_as_shared() -> None:
    """src.core.agents.models moet als shared geclassificeerd zijn.

    Statische check: MODULE_MAP entry aanwezig in dsm_full_analysis.py.
    Patroon: auth.models + workflow.models zijn al shared -- ORM data definitions.
    Sluit tenancy->agent_runtime edge (quota_middleware.py:117 lazy import).
    """
    content = Path("scripts/dsm_full_analysis.py").read_text(encoding="utf-8")
    assert '"src.core.agents.models": "shared"' in content, (
        "MODULE_MAP mist entry voor src.core.agents.models -> shared. "
        "Vereist voor SP-DSM-017 dag 1 tenancy->agent_runtime=0."
    )


@pytest.mark.architecture
def test_dsm017_tenancy_agent_runtime_edge_is_zero() -> None:
    """tenancy->agent_runtime moet 0 zijn na SP-DSM-017 dag 1 MODULE_MAP fix.

    Backward dep: quota_middleware.py:117 lazy import from src.core.agents.models.
    Fix: agents.models -> shared in MODULE_MAP.
    """
    from scripts.dsm_full_analysis import SOURCE_DIRS, scan_module

    counts, _, _ = scan_module("tenancy", SOURCE_DIRS.get("tenancy", []))
    terug = counts.get("agent_runtime", 0)
    assert terug == 0, (
        f"tenancy->agent_runtime = {terug} (verwacht 0 na SP-DSM-017 dag 1). "
        "Fix: agents.models -> shared in MODULE_MAP."
    )
