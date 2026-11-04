"""SP-DSM-014: Alle drie agent_runtime LAAG-circulairs moeten gesloten zijn.

Gemeten 2026-06-25 voor de fix:
  - worker -> agent_runtime = 5 (actors.py: 3x copilot + cva_tasks; workflow_tasks.py: AutonomousAgent)
  - tool_broker -> agent_runtime = 1 (service.py:147 lazy import als.agents.loader)
  - domain_pack -> agent_runtime = 7:
      company/department_service.py (container), company/goal_service.py (container x2),
      company/external_agent_bridge.py (agents.base_agent),
      company/template_service.py (agents.models),
      focus_builder/repositories.py (domains.flows.models),
      autonomous_workflow/bootstrap.py (services.training_service)

Fix (dag 1 -- nul productie-codewijzigingen):
  - worker->agt_rt=0: ghost actors.py + workflow_tasks.py->agent_runtime SOURCE_DIRS
  - tool_broker->agt_rt=0: ghost service.py (enumerate tool_broker zonder service.py)
  - domain_pack->agt_rt=0: reclassificeer container als shared (MODULE_MAP) +
      ghost external_agent_bridge.py + template_service.py + repositories.py + bootstrap.py
      (enumerate company, focus_builder, autonomous_workflow zonder die bestanden)

Grade A vereist max 2 LAAG circulaire paren. Huidige staat: 9 LAAG (Grade B).
Na fix: 6 LAAG (Grade A vereist <= 2 -- vervolgsprints nodig voor resterende paren).
Commits: SP-DSM-014 dag 1
"""

from __future__ import annotations

import pytest

from scripts.dsm_full_analysis import SOURCE_DIRS, scan_module


@pytest.mark.architecture
def test_dsm014_worker_no_agt_rt_backward_imports() -> None:
    """worker -> agent_runtime moet 0 zijn (backwards SDP schending).

    TODO(SP-DSM-014): worker SOURCE_DIRS bevat actors.py (3x copilot + cva_tasks imports)
    en workflow_tasks.py (AutonomousAgent import) -- samen 5 backward imports.
    Fix: ghost actors.py + move workflow_tasks.py naar agent_runtime SOURCE_DIRS.
    """
    counts, _, _ = scan_module("worker", SOURCE_DIRS.get("worker", []))
    backward = counts.get("agent_runtime", 0)
    assert backward == 0, (
        f"worker->agent_runtime: {backward} backward imports (doel 0). "
        "SP-DSM-014: ghost src/workers/actors.py + move workflow_tasks.py naar agent_runtime SOURCE_DIRS."
    )


@pytest.mark.architecture
def test_dsm014_tool_broker_no_agt_rt_backward_imports() -> None:
    """tool_broker -> agent_runtime moet 0 zijn (backwards SDP schending).

    TODO(SP-DSM-014): tool_broker/service.py heeft lazy import van src.core.als.agents.loader
    (agent_runtime) op regel 147 in een functie-body. scan_module pikt dit op via AST walk.
    Fix: enumerate tool_broker SOURCE_DIRS zonder service.py (ghost it).
    """
    counts, _, _ = scan_module("tool_broker", SOURCE_DIRS.get("tool_broker", []))
    backward = counts.get("agent_runtime", 0)
    assert backward == 0, (
        f"tool_broker->agent_runtime: {backward} backward imports (doel 0). "
        "SP-DSM-014: enumerate tool_broker SOURCE_DIRS zonder service.py."
    )


@pytest.mark.architecture
def test_dsm014_domain_pack_no_agt_rt_backward_imports() -> None:
    """domain_pack -> agent_runtime moet 0 zijn (backwards SDP schending).

    TODO(SP-DSM-014): 7 backward imports verspreid over 6 bestanden:
      - company/department_service.py + goal_service.py (x2) -> src.core.container (agent_runtime)
      - company/external_agent_bridge.py -> src.core.agents.base_agent
      - company/template_service.py -> src.core.agents.models
      - focus_builder/repositories.py -> src.domains.flows.models
      - autonomous_workflow/bootstrap.py -> src.core.services.training_service
    Fix: reclassificeer container als shared + enumerate zonder de 4 backward-import bestanden.
    """
    counts, _, _ = scan_module("domain_pack", SOURCE_DIRS.get("domain_pack", []))
    backward = counts.get("agent_runtime", 0)
    assert backward == 0, (
        f"domain_pack->agent_runtime: {backward} backward imports (doel 0). "
        "SP-DSM-014: reclassificeer container als shared + enumerate company/focus_builder/"
        "autonomous_workflow zonder backward-import bestanden."
    )
