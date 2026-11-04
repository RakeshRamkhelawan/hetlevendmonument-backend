"""
Unit tests: cache tenant isolatie -- SP-SEC-001 TI-001..005

Verifieer dat cache-sleutels per tenant uniek zijn.
Alle tests zijn RED voor de fix, GREEN na de fix.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# TI-001: cache_layer.cached() -- decorator
# ---------------------------------------------------------------------------


async def test_cache_layer_key_differs_per_tenant():
    """cached() decorator must generate different cache keys per tenant_id -- TI-001."""
    from src.core.caching.cache_layer import cached
    from src.core.middleware.tenant_context import _tenant_context

    captured_keys: list[str] = []

    mock_cache = MagicMock()
    mock_cache.get = AsyncMock(return_value=None)

    async def capture_set(key: str, value: object, ttl: int) -> bool:
        captured_keys.append(key)
        return True

    mock_cache.set = AsyncMock(side_effect=capture_set)
    mock_cache.connected = True

    @cached(key_prefix="test", ttl=60)
    async def sample_fn(x: int) -> int:
        return x * 2

    async def fake_get_cache() -> MagicMock:
        return mock_cache

    with patch("src.core.caching.cache_layer.get_cache", side_effect=fake_get_cache):
        tok1 = _tenant_context.set(1)
        try:
            await sample_fn(42)
        finally:
            _tenant_context.reset(tok1)

        tok2 = _tenant_context.set(2)
        try:
            await sample_fn(42)  # identical args, different tenant
        finally:
            _tenant_context.reset(tok2)

    assert len(captured_keys) == 2, f"Expected 2 cache.set calls, got {len(captured_keys)}"
    assert captured_keys[0] != captured_keys[1], (
        f"Cache keys must differ per tenant. Got identical key: {captured_keys[0]!r}. "
        "Fix: add get_tenant_id() prefix to cache_key in cache_layer.py (SP-SEC-001 TI-001)."
    )


# ---------------------------------------------------------------------------
# TI-002: embedding_service.py -- generate_embedding()
# ---------------------------------------------------------------------------


async def test_embedding_service_cache_key_differs_per_tenant():
    """generate_embedding() must use different cache keys per tenant_id -- TI-002."""
    from src.core.knowledge.embedding_service import EmbeddingService, EmbeddingModel
    from src.core.middleware.tenant_context import _tenant_context

    get_calls: list[str] = []

    mock_cache = MagicMock()

    async def capture_get(key: str) -> None:
        get_calls.append(key)
        return None  # always cache miss

    mock_cache.get = AsyncMock(side_effect=capture_get)
    mock_cache.set = AsyncMock(return_value=True)

    with patch("src.core.knowledge.embedding_service.cache_system", mock_cache):
        service = EmbeddingService(model=EmbeddingModel.MOCK_EMBEDDING)
        service._initialized = True

        tok1 = _tenant_context.set(1)
        try:
            await service.generate_embedding("hello world")
        finally:
            _tenant_context.reset(tok1)

        tok2 = _tenant_context.set(2)
        try:
            await service.generate_embedding("hello world")  # same text, different tenant
        finally:
            _tenant_context.reset(tok2)

    assert len(get_calls) >= 2, f"Expected at least 2 cache.get calls, got {len(get_calls)}"
    assert get_calls[0] != get_calls[1], (
        f"Embedding cache keys must differ per tenant. Got identical key: {get_calls[0]!r}. "
        "Fix: add tenant_id prefix to cache_key in embedding_service.py (SP-SEC-001 TI-002)."
    )


# ---------------------------------------------------------------------------
# TI-003: performance_middleware.py -- cached_response() decorator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_performance_middleware_cache_key_differs_per_tenant():
    """cached_response() must produce different keys for different tenant contexts -- TI-003."""
    from unittest.mock import patch
    from src.core.api.performance_middleware import cached_response, performance_cache

    captured_keys: list[str] = []

    def spy_get(key: str):
        captured_keys.append(key)
        return None  # always miss so the wrapped function executes

    performance_cache.clear()

    @cached_response(ttl=60)
    async def _dummy(x: int) -> int:
        return x

    with (
        patch.object(performance_cache, "get", side_effect=spy_get),
        patch.object(performance_cache, "set"),
    ):
        with patch("src.core.api.performance_middleware.get_tenant_id", return_value=10):
            await _dummy(1)
        with patch("src.core.api.performance_middleware.get_tenant_id", return_value=20):
            await _dummy(1)

    assert len(captured_keys) >= 2, "Expected at least 2 cache lookups (one per tenant)"
    assert captured_keys[0] != captured_keys[1], (
        f"cache_key must differ per tenant -- TI-003. Got identical: {captured_keys[0]!r}"
    )
    assert "t10:" in captured_keys[0] or "10" in captured_keys[0], (
        f"cache_key must embed tenant id -- TI-003. Got: {captured_keys[0]!r}"
    )


# ---------------------------------------------------------------------------
# TI-004: intelligent_router.py -- select_provider()
# ---------------------------------------------------------------------------


def test_intelligent_router_cache_key_includes_tenant_id():
    """select_provider() must include tenant_id in router cache key -- TI-004."""
    import inspect
    from src.core.llm.intelligent_router import IntelligentRouter

    source = inspect.getsource(IntelligentRouter.select_provider)
    assert "tenant_id" in source, (
        "IntelligentRouter.select_provider() must include tenant_id in router_selection cache key. "
        "Fix: import get_tenant_id() and prefix cache_key with tenant_id "
        "in intelligent_router.py (SP-SEC-001 TI-004)."
    )


# ---------------------------------------------------------------------------
# TI-005: goal_service.py -- get_ancestry()
# ---------------------------------------------------------------------------


async def test_goal_service_ancestry_cache_key_differs_per_tenant():
    """get_ancestry() must use different Redis cache keys per tenant_id -- TI-005."""
    import uuid

    captured_keys: list[str] = []

    mock_redis = MagicMock()

    async def capture_get(key: str) -> None:
        captured_keys.append(key)
        return None  # cache miss -- triggers DB path

    mock_redis.get = AsyncMock(side_effect=capture_get)
    mock_redis.setex = AsyncMock(return_value=True)
    mock_redis.set = AsyncMock(return_value=True)

    mock_db = MagicMock()
    mock_tenant = MagicMock()
    mock_tenant.tenant_id = 1

    from src.core.company.goal_service import GoalService

    service = GoalService(db_manager=mock_db, tenant_context=mock_tenant)
    service._redis = mock_redis

    goal_id = uuid.uuid4()

    # Mock the DB path to avoid actual DB calls (returns empty ancestry)
    async def mock_execute(query: str, params: dict | None = None, readonly: bool = True):  # type: ignore[type-arg]
        return []

    service._execute = mock_execute  # type: ignore[method-assign]

    # GoalService uses self._tenant.tenant_id (injected context), not ContextVar (QR-011)
    mock_tenant.tenant_id = 1
    await service.get_ancestry(goal_id)

    mock_tenant.tenant_id = 2
    await service.get_ancestry(goal_id)

    assert len(captured_keys) >= 2, f"Expected at least 2 Redis.get calls, got {len(captured_keys)}"
    assert captured_keys[0] != captured_keys[1], (
        f"Ancestry cache keys must differ per tenant. Got identical key: {captured_keys[0]!r}. "
        "Fix: add tenant_id prefix to cache_key in goal_service.py (SP-SEC-001 TI-005)."
    )
