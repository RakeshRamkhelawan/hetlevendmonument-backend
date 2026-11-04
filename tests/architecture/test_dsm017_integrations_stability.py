"""DSM-017 Dag 2: integrations stabiliteits-monitoring.

P2 aanbeveling uit DSM audit 2026-06-26: integrations I=0.535 zonder formele ceiling.
Deze tests leggen een ceiling vast zodat regressies vroeg worden gevangen.

Baseline 2026-06-26:
  Ce_excl_shared = 40 (budget 60 -- comfortabel)
  I = 0.535 (Ce_all=85, Ca=74)
"""

from __future__ import annotations

import pytest

from scripts.dsm_full_analysis import SOURCE_DIRS, scan_module


@pytest.mark.architecture
def test_dsm017_integrations_ce_excl_shared_within_budget() -> None:
    """integrations Ce_excl_shared <= 65 (budget 60 + 5 buffer).

    Baseline 2026-06-26: Ce_excl_shared=40 (infra=31, auth=5, governance=2, worker=2).
    Budget 60 is het DSM audit maximum; 5 buffer voor commit-batch drift.
    """
    counts, _, _ = scan_module("integrations", SOURCE_DIRS.get("integrations", []))
    ce_excl_shared = sum(v for k, v in counts.items() if k != "shared")
    assert ce_excl_shared <= 65, (
        f"integrations Ce_excl_shared = {ce_excl_shared} (max 65, budget 60 + buffer). "
        f"Verdeling: { {k: v for k, v in counts.items() if k != 'shared'} }. "
        "SP-DSM-017 dag 2 regressie-alarm."
    )


@pytest.mark.architecture
def test_dsm017_integrations_instability_below_0_60() -> None:
    """integrations I <= 0.60 (ceiling; baseline I=0.535).

    I = Ce / (Ce + Ca). Ce inclusief shared (Ce_all=85, Ca=74, I=0.535).
    NOTE: Ce_all wijkt af van calculate_instability() die Ce_excl_shared (=40) gebruikt.
    Deze test monitort de DSM audit-baseline (inclusief shared) voor consistentie met het rapport.
    Baseline 2026-06-26: Ce_all=85, Ca=74, I=0.535.
    """
    counts, _, _ = scan_module("integrations", SOURCE_DIRS.get("integrations", []))
    ce = sum(counts.values())
    ca = sum(
        scan_module(m, SOURCE_DIRS.get(m, []))[0].get("integrations", 0)
        for m in SOURCE_DIRS
        if m != "integrations"
    )
    i_value = ce / (ce + ca) if (ce + ca) > 0 else 0.0
    assert i_value <= 0.60, (
        f"integrations I = {i_value:.3f} (max 0.60, baseline 0.535). "
        f"Ce={ce}, Ca={ca}. "
        "SP-DSM-017 dag 2 regressie-alarm."
    )
