"""DSM governance I-regressie tracking tests.

governance->agent_runtime runtime coupling is 0:
  - LearningInsight / AdaptationRule -> shared (SP-DSM-REGRESSIE dag 1, commit 0cc54e93)
  - C7Workflow -> shared (SP-DSM-REGRESSIE dag 1, commit 0cc54e93)
  - EmailService -> integrations (SP-DSM-REGRESSIE dag 1, commit 0cc54e93)

infra->governance backward dep is 0 (SP-DSM-012 dag 1):
  - tenant_query_filter.py: governance import verwijderd, __tablename__ check gebruikt
  - models/__init__.py: AuditLog re-export verwijderd (dode code, model_registry dekte dit al)
"""

from __future__ import annotations

import pytest

from scripts.dsm_full_analysis import SOURCE_DIRS, scan_module


@pytest.mark.architecture
def test_governance_no_agent_runtime_runtime_import() -> None:
    """governance MOET 0 runtime imports naar agent_runtime hebben.

    TODO(SP-DSM-REGRESSIE): governance->agent_runtime = 10 door leer-/workflow-/email-
    imports in compliance en DSAR code. Fix: MODULE_MAP reclassificatie naar shared/integrations.
    """
    counts, _, _ = scan_module("governance", SOURCE_DIRS.get("governance", []))
    agent_runtime_imports = counts.get("agent_runtime", 0)
    assert agent_runtime_imports == 0, (
        f"governance->agent_runtime = {agent_runtime_imports} (verwacht 0). "
        "MODULE_MAP: src.core.learning.loop + src.core.workflow.models -> 'shared', "
        "src.core.services.email -> 'integrations'"
    )


@pytest.mark.architecture
def test_infra_no_governance_imports() -> None:
    """infra->governance MOET 0 zijn. Gefixed in SP-DSM-012 dag 1.

    Fix 1: tenant_query_filter.py -- governance import verwijderd, __tablename__ check gebruikt.
    Fix 2: models/__init__.py -- AuditLog re-export verwijderd (model_registry dekte dit al).
    """
    counts, _, _ = scan_module("infra", SOURCE_DIRS.get("infra", []))
    governance_imports = counts.get("governance", 0)
    assert governance_imports == 0, (
        f"infra->governance = {governance_imports} (verwacht 0, SDP-schending). "
        "SP-DSM-012: governance import verwijderd uit tenant_query_filter.py "
        "(gebruik __tablename__ guard) + AuditLog verwijderd uit models/__init__.py."
    )
