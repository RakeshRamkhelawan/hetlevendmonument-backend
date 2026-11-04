"""DSM arch-tests: auth SDP fix -- SP-DSM-REGRESSIE dag 2.

auth (I=0.06) importeerde 5x van agent_runtime via src.core.services.rbac_service.
Fix: MODULE_MAP reclassificatie rbac_service -> auth (RBAC is auth-concern).
"""

import pytest
from scripts.dsm_full_analysis import SOURCE_DIRS, scan_module


@pytest.mark.architecture
def test_auth_no_agent_runtime_import() -> None:
    """auth -> agent_runtime = 0: RBAC service reclassificeerd naar auth bucket.

    Achtergrond: src.core.services.rbac_service stond in MODULE_MAP als
    agent_runtime (via src.core.services catch-all). Alle 5 auth->agent_runtime
    backward deps liepen via dit bestand. Na reclassificatie zijn het auth->auth
    imports (zelfde bucket, niet geteld). SP-DSM-REGRESSIE dag 2.
    """
    counts, _, _ = scan_module("auth", SOURCE_DIRS.get("auth", []))
    ar_imports = counts.get("agent_runtime", 0)
    assert ar_imports == 0, (
        f"auth->agent_runtime = {ar_imports} (verwacht 0). "
        "MODULE_MAP: src.core.services.rbac_service moet 'auth' zijn."
    )
