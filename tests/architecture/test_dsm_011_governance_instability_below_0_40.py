"""SP-DSM-011: governance instabiliteit moet onder 0.40 blijven.

Root cause was: src.core.governance.models fout geclassificeerd als 'shared' (22 interne
imports telden als governance->shared). Bovendien: event_handlers + dsar_notifications staan
in governance SOURCE_DIRS terwijl ze logisch worker/integrations zijn.

Fix (SP-DSM-011 dag 1): governance.models terug naar governance (verwijder MODULE_MAP override)
+ event_handlers -> worker + dsar_notifications -> integrations via SOURCE_DIRS chirurgie.
"""

from __future__ import annotations

import pytest

from scripts.dsm_full_analysis import SOURCE_DIRS, scan_module


@pytest.mark.architecture
def test_dsm_011_governance_instability_below_0_40() -> None:
    """governance I moet < 0.40 zijn (SP-DSM-011 governance_worker pattern).

    Gemeten na SP-DSM-011 dag 1: I=0.373 (Ce=38, Ca=64).
    """
    counts, _, _ = scan_module("governance", SOURCE_DIRS.get("governance", []))
    gov_ce = sum(counts.values())
    gov_ca = sum(
        scan_module(m, SOURCE_DIRS.get(m, []))[0].get("governance", 0)
        for m in SOURCE_DIRS
        if m != "governance"
    )
    i_value = gov_ce / (gov_ce + gov_ca) if (gov_ce + gov_ca) > 0 else 0.0
    assert i_value < 0.40, (
        f"governance I = {i_value:.3f} (verwacht < 0.40, SP-DSM-011). "
        "Regressie: controleer governance.models, event_handlers, dsar_notifications "
        "entries in MODULE_MAP en SOURCE_DIRS in scripts/dsm_full_analysis.py."
    )
