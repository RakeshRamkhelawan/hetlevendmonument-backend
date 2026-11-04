"""DSM regression: API-layer direct imports of forbidden modules.

This test guards ADR-033. Current baseline is captured by API_VIOLATION_CEILING.
As violations are fixed, lower the ceiling. New violations fail the build.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parents[2]
_FINDER_SCRIPT = _REPO_ROOT / "scripts" / "dsm_api_violation_finder.py"

# Baseline 15 juni 2026: 76 files / 152 direct forbidden imports in API-layer.
# SP-DSM-002 Dag 1 (16 juni 2026): 7 bestanden gefixed (cva, agentic, als x2, gatekeeper, admin_digital_twin, stripe).
# 152 -> 127 violations (-25). Lower this number as violations are migrated to *.dependencies.py facades.
# SP-DSM-002 Dag 2 (16 juni 2026): api/learning.py Strangler Fig -> v1/learning/ (-10 violations).
# 127 -> 117 violations.
# SP-DSM-002 Dag 3 (16 juni 2026): Groep C bootstrap-exempt (main.py, lifecycle.py, _prana_contracts_cache.py).
# activepieces governance.rate_limiter batch (-4). 117 -> 100 violations.
# SP-DSM-002 Dag 4 (16 juni 2026): governance.audit + database.* + services.rbac/experiment big batch.
# documents, tenant_mgmt, user_mgmt, rbac, admin, company, health, copilot_intent, experimentation, cva.
# 100 -> 64 violations (-36).
# SP-DSM-002 Dag 5 (17 juni 2026): services.* + privacy + webhooks + agents + models + autonomous batch.
# workflow, feature_flags, ai_act, missions, board, analytics, privacy, webhooks, agents, knowledge,
# tenants, analytics/benchmarks, autonomous, models. 64 -> 35 violations (-29).
# SP-DSM-002 Dag 5 FA-fixes (17 juni 2026): benchmarks f-string, webhook ADR-003 comment, ceiling 36 -> 35.
# SP-DSM-002 Dag 6 (17 juni 2026): Cluster A dsm:exempt + Cluster B agentic/als + Cluster C cva +
# Cluster D focus_builder + Cluster E sync/ws_handler. 35 -> 0 violations. SP-DSM-002 CLOSED.
API_VIOLATION_CEILING = 0


def _count_violations() -> int:
    result = subprocess.run(
        [sys.executable, str(_FINDER_SCRIPT)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("Total violations found:"):
            return int(line.split(":")[-1].strip())
    raise RuntimeError("Could not parse violation count from finder output")


@pytest.mark.architecture
def test_api_layer_violations_regression_ceiling() -> None:
    """API-layer direct imports of forbidden modules may not increase."""
    count = _count_violations()
    assert count <= API_VIOLATION_CEILING, (
        f"DSM: API-layer direct forbidden imports increased from "
        f"{API_VIOLATION_CEILING} to {count}. "
        f"Run: python scripts/dsm_api_violation_finder.py"
    )


@pytest.mark.architecture
def test_api_layer_violations_trending_down() -> None:
    """Fails when ceiling can be lowered (notification, not blocking)."""
    count = _count_violations()
    # When count drops 10% below ceiling, the ceiling should be updated.
    if count < API_VIOLATION_CEILING * 0.9:
        pytest.xfail(
            f"DSM: violation count dropped to {count}; "
            f"lower API_VIOLATION_CEILING in {Path(__file__).name}"
        )
