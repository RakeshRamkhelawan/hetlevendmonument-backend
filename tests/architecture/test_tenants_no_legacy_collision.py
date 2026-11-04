"""AUDIT-DB-01: legacy tenant_management router must not collide with new tenants router."""

from pathlib import Path

import pytest


@pytest.mark.architecture
def test_app_factory_does_not_register_legacy_tenant_management() -> None:
    """Deprecated app_factory must not include v1/tenant_management domain_router.

    The canonical src.main factory registers routers via router_registry,
    which uses the new src.core.api.v1.tenants package. Including the legacy
    tenant_management router in app_factory would create a route collision on
    /api/v1/tenants/.
    """
    app_factory_path = Path(__file__).parents[2] / "src" / "core" / "app_factory.py"
    source = app_factory_path.read_text(encoding="utf-8")

    assert (
        "tenant_management" not in source or "domain_router as tenant_domain_router" not in source
    ), (
        "Legacy tenant_management domain_router is still registered in app_factory; "
        "this causes a route collision with the new tenants registry."
    )
