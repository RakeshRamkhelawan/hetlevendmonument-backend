"""SP-DSM-010: integrations -> agent_runtime reverse imports moeten 0 zijn.

Root cause was: src.core.collaboration (task_distributor), src.core.events.handlers
(learning_event_handler + workflow_handler), src.core.activepieces.indexer, en
src.core.protocol.unified_message_protocol waren fout geclassificeerd als integrations.

Fix (SP-DSM-010 dag 1, commit 8352eafc): MODULE_MAP reclassificatie:
- src.core.collaboration -> agent_runtime (was: integrations)
- src.core.events.handlers -> agent_runtime (specifieke prefix)
- src.core.activepieces.indexer -> agent_runtime (specifieke prefix)
- src.core.protocol.unified_message_protocol -> agent_runtime (specifieke prefix)
"""

from __future__ import annotations

import pytest

from scripts.dsm_full_analysis import SOURCE_DIRS, scan_module


@pytest.mark.architecture
def test_dsm_010_integrations_no_agent_runtime_reverse_import() -> None:
    """integrations -> agent_runtime MOET 0 zijn (SDP: integrations I=0.40 < agent_runtime I=0.47).

    Gesloten door SP-DSM-010 dag 1 via MODULE_MAP reclassificatie. Gemeten 2026-06-24.
    """
    counts, _, _ = scan_module("integrations", SOURCE_DIRS.get("integrations", []))
    reverse_count = counts.get("agent_runtime", 0)
    assert reverse_count == 0, (
        f"integrations->agent_runtime = {reverse_count} (verwacht 0, SDP-schending). "
        "Regressie: controleer recente MODULE_MAP wijzigingen in scripts/dsm_full_analysis.py. "
        "Referentie: SP-DSM-010 reclassificaties (collaboration, events.handlers, "
        "activepieces.indexer, protocol.unified_message_protocol -> agent_runtime)."
    )
