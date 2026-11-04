# tests/unit/test_monetization_phase1_behavioral.py
from unittest.mock import AsyncMock

import pytest

from src.core.models.rbac_models import Tenant
from src.core.services.subscription_cache import TenantSubscriptionCache


@pytest.mark.unit
@pytest.mark.asyncio
async def test_behavioral_1_b_1_cache_hit_functionaliteit():
    """
    Test 1.B.1 (Cache-Hit Functionaliteit):
    De console vraagt de billing status op; het systeem laadt de gegevens correct
    uit Redis zonder een database-query uit te voeren.
    """
    mock_cache = AsyncMock()
    mock_cache.get.return_value = {"tier": "enterprise", "status": "active"}

    # We initialiseren de cache service met een mock cache layer
    service = TenantSubscriptionCache(tenant_id=42, cache_layer=mock_cache)

    # We vragen de abonnementsgegevens op
    result = await service.get()

    # Controleer of de gegevens exact overeenkomen met wat er in de cache (Redis) zat
    assert result == {"tier": "enterprise", "status": "active"}

    # Verifieer dat Redis daadwerkelijk is geraadpleegd met de correcte tenant-sleutel
    mock_cache.get.assert_awaited_once_with("tenant_sub:42")


@pytest.mark.unit
def test_behavioral_1_b_2_model_validation():
    """
    Test 1.B.2 (Model Validatie):
    Pogingen om een ongeldige abonnementsvorm (bijv. "ultra-pro") toe te wijzen
    aan het model resulteren in een ValueError.
    """
    tenant = Tenant(name="Behavioral Test Tenant", slug="beh-test-tenant")

    # Een geldige tier moet worden geaccepteerd
    tenant.subscription_tier = "starter"
    assert tenant.subscription_tier == "starter"

    # Een ongeldige tier moet leiden tot een ValueError
    with pytest.raises(ValueError) as exc_info:
        tenant.subscription_tier = "ultra-pro"
    assert "Invalid subscription tier" in str(exc_info.value)


@pytest.mark.unit
def test_behavioral_1_b_3_nullable_semantics():
    """
    Test 1.B.3 (Nullable Semantiek):
    Als een tenant expliciet de waarde None krijgt toegewezen voor subscription_tier,
    blijft deze None in plaats van stilzwijgend te worden geconverteerd naar 'free'.
    """
    tenant = Tenant(name="Behavioral Test Tenant 2", slug="beh-test-tenant-2")

    # Expliciete toewijzing van None
    tenant.subscription_tier = None
    assert tenant.subscription_tier is None

    # Hetzelfde geldt voor subscription_status
    tenant.subscription_status = None
    assert tenant.subscription_status is None
