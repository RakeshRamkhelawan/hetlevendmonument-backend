"""DSM tracking tests: resterende MEDIUM/LAAG paren na SP-DSM-REGRESSIE dag 2.

Deze tests leggen het huidige maximum vast voor elk paar dat nog niet
gefixd is. Ze zijn GROEN (maximum niet overschreden) en worden ROOD
als een toekomstige wijziging het aantal imports vergroot.

P2 backlog: volledig oplossen vereist ADR-025 event-bus activatie.
Sprint-backlog item: SP-DSM-010.
"""

import pytest
from scripts.dsm_full_analysis import SOURCE_DIRS, scan_module


# ---------------------------------------------------------------------------
# LAAG: agent_runtime <-> integrations (na SP-DSM-010)
# integrations -> agent_runtime (0 terug) = backward dep OPGELOST (SP-DSM-010)
# agent_runtime -> integrations (33 heen) = forward dep (SDP-conform)
# Reclassificaties SP-DSM-010: collaboration + events/handlers + events/learning_event_wiring
# + activepieces/indexer + protocol/ -> agent_runtime. Heen gemeten 2026-06-24.
# Fix vereist: ADR-025 event-bus (agent_runtime -> integrations reduceren)
# ---------------------------------------------------------------------------


@pytest.mark.architecture
def test_agent_runtime_integrations_heen_not_growing() -> None:
    """agent_runtime->integrations mag niet groeien boven 33. Gemeten 2026-06-24 (SP-DSM-010)."""
    counts, _, _ = scan_module("agent_runtime", SOURCE_DIRS.get("agent_runtime", []))
    heen = counts.get("integrations", 0)
    assert heen <= 33, (
        f"agent_runtime->integrations = {heen} (max 33, SDP-conform forward dep). "
        "SP-DSM-010: collaboration+events/handlers+protocol reclassificatie -> agent_runtime."
    )


@pytest.mark.architecture
def test_integrations_agent_runtime_terug_not_growing() -> None:
    """integrations->agent_runtime (backward dep) moet 0 zijn na SP-DSM-010."""
    counts, _, _ = scan_module("integrations", SOURCE_DIRS.get("integrations", []))
    terug = counts.get("agent_runtime", 0)
    assert terug == 0, (
        f"integrations->agent_runtime = {terug} (verwacht 0 na SP-DSM-010 reclassificatie). "
        "Root cause: collaboration + events/handlers + activepieces/indexer "
        "zijn herclassificeerd naar agent_runtime."
    )


# ---------------------------------------------------------------------------
# LAAG: agent_runtime <-> domain_pack
# domain_pack -> agent_runtime (7 terug) = backward dep
# Root cause: company/*, focus_builder/repositories, autonomous_workflow/bootstrap
# Fix vereist: container/agents.models reclassificatie of DI-aanpassing (P3)
# TODO(SP-DSM-011): verwijder dit als domain_pack -> agent_runtime = 0
# ---------------------------------------------------------------------------


@pytest.mark.architecture
def test_agent_runtime_domain_pack_heen_not_growing() -> None:
    """agent_runtime->domain_pack mag niet groeien boven 11. Gemeten 2026-06-24."""
    counts, _, _ = scan_module("agent_runtime", SOURCE_DIRS.get("agent_runtime", []))
    heen = counts.get("domain_pack", 0)
    assert heen <= 11, f"agent_runtime->domain_pack = {heen} (max 11). SP-DSM-011 backlog."


@pytest.mark.architecture
def test_domain_pack_agent_runtime_terug_not_growing() -> None:
    """domain_pack->agent_runtime (backward dep) mag niet groeien boven 7. Gemeten 2026-06-24."""
    counts, _, _ = scan_module("domain_pack", SOURCE_DIRS.get("domain_pack", []))
    terug = counts.get("agent_runtime", 0)
    assert terug <= 7, (
        f"domain_pack->agent_runtime = {terug} (max 7, backward dep). SP-DSM-011 backlog."
    )


# ---------------------------------------------------------------------------
# LAAG: agent_runtime <-> tool_broker
# tool_broker -> agent_runtime (1 terug) = minimale backward dep
# Root cause: enkelvoudige import, deels TYPE_CHECKING-achtig
# TODO(SP-DSM-012): verwijder als tool_broker -> agent_runtime = 0
# ---------------------------------------------------------------------------


@pytest.mark.architecture
def test_tool_broker_agent_runtime_terug_not_growing() -> None:
    """tool_broker->agent_runtime mag niet groeien boven 1. Gemeten 2026-06-24."""
    counts, _, _ = scan_module("tool_broker", SOURCE_DIRS.get("tool_broker", []))
    terug = counts.get("agent_runtime", 0)
    assert terug <= 1, f"tool_broker->agent_runtime = {terug} (max 1). SP-DSM-012 backlog."


# ---------------------------------------------------------------------------
# LAAG: tenancy -> agent_runtime (GESLOTEN SP-DSM-017 dag 1)
# tenancy -> agent_runtime = 0 na agents.models -> shared reclassificatie
# Fix: src.core.agents.models -> shared in MODULE_MAP (quota_middleware.py:117)
# ---------------------------------------------------------------------------


@pytest.mark.architecture
def test_tenancy_agent_runtime_terug_not_growing() -> None:
    """tenancy->agent_runtime moet 0 zijn na SP-DSM-017 dag 1."""
    counts, _, _ = scan_module("tenancy", SOURCE_DIRS.get("tenancy", []))
    terug = counts.get("agent_runtime", 0)
    assert terug == 0, (
        f"tenancy->agent_runtime = {terug} (verwacht 0, GESLOTEN SP-DSM-017 dag 1). "
        "Regressie: controleer agents.models entry in MODULE_MAP."
    )


# ---------------------------------------------------------------------------
# LAAG: tenancy -> governance (3 heen) = backward dep (tenancy=2, governance=3)
# Root cause: audit_middleware.py:384 (governance.audit), quota_middleware.py:18
# + tenant_middleware.py:37 (governance.services.audit_service).
# MODULE_MAP aanpak reduceert governance Ca waardoor I > 0.40 (geblokkeerd).
# Fix vereist: SecurityEvent + log_security_event verplaatsen naar shared module.
# ---------------------------------------------------------------------------


@pytest.mark.architecture
def test_SP_DSM_019_tenancy_governance_backward_is_zero() -> None:
    """tenancy->governance == 0 -- gesloten in SP-DSM-019 dag 1.

    Fix: SecurityEvent + log_security_event naar src/core/shared/security_events.py verplaatst.
    Dead code log_learning_audit_event verwijderd uit audit_middleware.py.
    """
    counts, _, _ = scan_module("tenancy", SOURCE_DIRS.get("tenancy", []))
    heen = counts.get("governance", 0)
    assert heen == 0, (
        f"tenancy->governance = {heen} (verwacht 0, gesloten SP-DSM-019). "
        "Regressie: check src/core/middleware/ op governance-imports."
    )


# ---------------------------------------------------------------------------
# LAAG: governance <-> infra (gefixed in SP-DSM-012 dag 1)
# governance -> infra (8 heen) = forward dep (SDP-conform)
# infra -> governance = 0 (SDP-schending opgelost)
# Fix: tenant_query_filter.py governance import verwijderd + models/__init__.py AuditLog verwijderd
# ---------------------------------------------------------------------------


@pytest.mark.architecture
def test_governance_infra_terug_not_growing() -> None:
    """infra->governance moet 0 zijn. Gefixed SP-DSM-012 dag 1, 2026-06-24."""
    counts, _, _ = scan_module("infra", SOURCE_DIRS.get("infra", []))
    terug = counts.get("governance", 0)
    assert terug == 0, (
        f"infra->governance = {terug} (verwacht 0, SDP-schending). SP-DSM-012 regressie."
    )
