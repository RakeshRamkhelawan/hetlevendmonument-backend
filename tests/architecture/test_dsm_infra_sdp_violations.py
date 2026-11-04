"""DSM infra SDP-schendingen tracking tests.

infra (I=0.039) mag NIET afhangen van hogere lagen:
- tenancy (I~0.13): tenant_context ContextVar imports
- domain_pack (I~0.38): procedures.models ORM-definitie imports
- integrations (I~0.40): connectors + pubsub imports
- worker (I~0.89): calendar_sync_worker Dramatiq import

ROOD totdat MODULE_MAP/SOURCE_DIRS fixes zijn doorgevoerd (SP-DSM-INFRA-001).
Alle vier tests GROEN na commit van dag 1.
"""

from __future__ import annotations

import pytest

from scripts.dsm_full_analysis import SOURCE_DIRS, scan_module


@pytest.mark.architecture
def test_infra_no_tenancy_import() -> None:
    """infra MOET 0 runtime imports naar tenancy hebben.

    TODO(SP-DSM-INFRA-001): infra->tenancy = 6 door tenant_context imports in
    database.py, tenant_query_filter.py, config/feature_flags.py,
    observability/logging.py, observability/metrics.py.
    Fix: src.core.middleware.tenant_context -> 'shared' in MODULE_MAP
    (ContextVar primitief -- cross-cutting infra, zoals auth.models).
    """
    counts, _, _ = scan_module("infra", SOURCE_DIRS.get("infra", []))
    tenancy_imports = counts.get("tenancy", 0)
    assert tenancy_imports == 0, (
        f"infra->tenancy = {tenancy_imports} (verwacht 0). "
        "MODULE_MAP: src.core.middleware.tenant_context -> 'shared'"
    )


@pytest.mark.architecture
def test_infra_no_domain_pack_import() -> None:
    """infra MOET 0 runtime imports naar domain_pack hebben.

    TODO(SP-DSM-INFRA-001): infra->domain_pack = 2 door procedures.models import
    in observability/audit_logger.py en observability/evaluation_repository.py.
    Fix: src.core.procedures.models -> 'shared' in MODULE_MAP
    (SQLAlchemy ORM model-definitie -- zoals governance.models en workflow.models).
    """
    counts, _, _ = scan_module("infra", SOURCE_DIRS.get("infra", []))
    domain_pack_imports = counts.get("domain_pack", 0)
    assert domain_pack_imports == 0, (
        f"infra->domain_pack = {domain_pack_imports} (verwacht 0). "
        "MODULE_MAP: src.core.procedures.models -> 'shared' (zoals governance.models)"
    )


@pytest.mark.architecture
def test_infra_no_integrations_import() -> None:
    """infra MOET 0 runtime imports naar integrations hebben.

    TODO(SP-DSM-INFRA-001): infra->integrations = 3:
    - cache_decorators.py:14: pubsub_manager (src.core.events)
      Fix: src.core.events.pubsub_manager -> 'infra' (Redis primitief, zoals resilience)
    - alert_notification_bridge.py:18-19: connectors.notification
      Fix: bestand uit SOURCE_DIRS['infra'] verplaatsen naar SOURCE_DIRS['integrations']
    """
    counts, _, _ = scan_module("infra", SOURCE_DIRS.get("infra", []))
    integrations_imports = counts.get("integrations", 0)
    assert integrations_imports == 0, (
        f"infra->integrations = {integrations_imports} (verwacht 0). "
        "Zie TODO(SP-DSM-INFRA-001): pubsub_manager -> 'infra' + alert_notification_bridge -> integrations"
    )


@pytest.mark.architecture
def test_infra_no_worker_import() -> None:
    """infra MOET 0 runtime imports naar worker hebben.

    TODO(SP-DSM-INFRA-001): infra->worker = 1 door
    scheduling/webhooks/handlers.py:200: calendar_sync_worker (Dramatiq).
    Fix: handlers.py uit SOURCE_DIRS['infra'] verplaatsen naar SOURCE_DIRS['worker']
    (webhook handler die workers triggert IS een worker-laag concern).
    """
    counts, _, _ = scan_module("infra", SOURCE_DIRS.get("infra", []))
    worker_imports = counts.get("worker", 0)
    assert worker_imports == 0, (
        f"infra->worker = {worker_imports} (verwacht 0). "
        "SOURCE_DIRS: scheduling/webhooks/handlers.py -> SOURCE_DIRS['worker']"
    )
