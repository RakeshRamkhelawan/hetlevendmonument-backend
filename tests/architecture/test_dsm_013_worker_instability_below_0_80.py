"""SP-DSM-013: worker instabiliteit moet onder 0.80 blijven.

Fix (dag 1): 6 bestanden uit worker SOURCE_DIRS reclassificeren:
  - calendar_sync_worker.py -> integrations
  - gdpr_purge.py -> integrations
  - webhooks/handlers.py -> integrations
  - cva_tasks.py -> agent_runtime
  - scheduler.py -> agent_runtime (schedules agent_runtime actors)
  - workflow_worker.py -> worker MODULE_MAP, niet in SOURCE_DIRS (ghost worker)

src.core.jobs blijft "worker" in MODULE_MAP + SOURCE_DIRS: alle 6 bestanden
importeren non-infra concerns (governance, agent_runtime, domain_pack).
Verplaatsen naar infra zou 4 SDP-constraints breken.

Resultaat: worker Ce 75->23, Ca 8->13, I 0.904->0.639 (commit: 8208de72).
"""

from __future__ import annotations

import pytest

from scripts.dsm_full_analysis import SOURCE_DIRS, scan_module


@pytest.mark.architecture
def test_dsm_013_worker_instability_below_0_80() -> None:
    """worker I moet < 0.80 zijn. Gefixed in SP-DSM-013 dag 1.

    TODO(SP-DSM-013): worker I=0.904 door calendar_sync_worker + core/jobs +
    gdpr_purge + cva_tasks + webhooks/handlers in worker SOURCE_DIRS (semantisch fout).
    Fix: reclassificatie naar integrations/infra/agent_runtime + MODULE_MAP overrides.
    """
    counts, _, _ = scan_module("worker", SOURCE_DIRS.get("worker", []))
    worker_ce = sum(counts.values())
    worker_ca = sum(
        scan_module(m, SOURCE_DIRS.get(m, []))[0].get("worker", 0)
        for m in SOURCE_DIRS
        if m != "worker"
    )
    i_value = worker_ce / (worker_ce + worker_ca) if (worker_ce + worker_ca) > 0 else 0.0
    assert i_value < 0.80, (
        f"worker I = {i_value:.3f} (verwacht < 0.80). "
        "SP-DSM-013: reclassificeer calendar_sync_worker + core/jobs + gdpr_purge "
        "+ cva_tasks + webhooks/handlers naar integrations/infra/agent_runtime "
        "in MODULE_MAP en SOURCE_DIRS van scripts/dsm_full_analysis.py."
    )
