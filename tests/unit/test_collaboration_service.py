"""
Tests for the CollaborationManager service.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initialize_sets_pubsub():
    """After initialize(), pubsub should not be None."""
    from src.core.services.collaboration_service import CollaborationManager

    manager = CollaborationManager()
    mock_redis = MagicMock()
    mock_pubsub = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub

    with patch("src.core.typing.create_async_redis_client", new_callable=AsyncMock) as mock_fn:
        mock_fn.return_value = mock_redis
        await manager.initialize()

    assert manager.pubsub is not None
    mock_redis.pubsub.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collaboration_manager_tenant_isolation():
    """Two CollaborationManager instances don't share redis connection."""
    from src.core.services.collaboration_service import CollaborationManager

    m1 = CollaborationManager()
    m2 = CollaborationManager()

    # Before initialization, both should have None redis
    assert m1.redis is None
    assert m2.redis is None

    # After initialization, they should either have different redis instances
    # or both remain None (depending on implementation)
    mock_redis = MagicMock()
    mock_pubsub = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub

    with patch("src.core.typing.create_async_redis_client", new_callable=AsyncMock) as mock_fn:
        mock_fn.return_value = mock_redis
        await m1.initialize()

    # m1 should have redis, m2 should still be None (different instances)
    assert m1.redis is not None
    assert m2.redis is None
    assert m1.redis is not m2.redis


@pytest.mark.unit
def test_collaboration_manager_attributes_typed():
    """CollaborationManager should have properly typed redis and pubsub attributes."""
    from src.core.services.collaboration_service import CollaborationManager

    manager = CollaborationManager()

    # Check that attributes exist and are initialized to None
    assert hasattr(manager, "redis")
    assert hasattr(manager, "pubsub")
    assert manager.redis is None
    assert manager.pubsub is None
