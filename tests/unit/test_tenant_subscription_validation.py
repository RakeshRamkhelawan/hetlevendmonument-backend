# tests/unit/test_tenant_subscription_validation.py
import pytest

from src.core.models.rbac_models import Tenant


@pytest.mark.unit
def test_tenant_subscription_tier_validation():
    tenant = Tenant(name="Valid Tenant", slug="valid-slug")

    # Geldige toewijzingen
    tenant.subscription_tier = "pro"
    assert tenant.subscription_tier == "pro"

    # Respecteer nullable semantiek (geen stiekeme coercie van None naar 'free')
    tenant.subscription_tier = None
    assert tenant.subscription_tier is None

    # Ongeldige toewijzing moet ValueError opwerpen
    with pytest.raises(ValueError) as exc_info:
        tenant.subscription_tier = "ultra-pro"
    assert "Invalid subscription tier" in str(exc_info.value)


@pytest.mark.unit
def test_tenant_subscription_status_validation():
    tenant = Tenant(name="Valid Tenant 2", slug="valid-slug-2")

    # Geldige toewijzing
    tenant.subscription_status = "trialing"
    assert tenant.subscription_status == "trialing"

    # Respecteer nullable semantiek
    tenant.subscription_status = None
    assert tenant.subscription_status is None

    # Ongeldige toewijzing moet ValueError opwerpen
    with pytest.raises(ValueError) as exc_info:
        tenant.subscription_status = "super-active"
    assert "Invalid subscription status" in str(exc_info.value)
