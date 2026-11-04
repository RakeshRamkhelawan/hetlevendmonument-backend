"""
Unit tests: single-tenant worker context decorator (AUDIT-ST-03).
"""


def test_worker_sets_tenant_id_in_single_tenant_mode(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "single_tenant")
    from src.core.workers.tenant_context import single_tenant_worker_context
    from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id

    set_tenant_id(None)
    with single_tenant_worker_context():
        assert get_tenant_id() == 1


def test_worker_does_not_override_existing_tenant_id(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "single_tenant")
    from src.core.workers.tenant_context import single_tenant_worker_context
    from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id

    set_tenant_id(42)
    with single_tenant_worker_context():
        assert get_tenant_id() == 42


def test_worker_no_override_in_saas_mode(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_MODE", "saas")
    from src.core.workers.tenant_context import single_tenant_worker_context
    from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id

    set_tenant_id(None)
    with single_tenant_worker_context():
        assert get_tenant_id() is None
