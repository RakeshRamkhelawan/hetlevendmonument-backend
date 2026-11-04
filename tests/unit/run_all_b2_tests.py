"""Run all B2 phase tests directly (bypasses pytest collection issues)."""

import asyncio
import inspect
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, ".")


def test_tenant_id_raises_without_context():
    with patch(
        "src.core.middleware.tenant_context.get_tenant_id", return_value=None
    ):
        from src.core.api.v1.feature_flags.dependencies import get_tenant_id

        try:
            get_tenant_id()
            raise AssertionError("Should have raised RuntimeError")
        except RuntimeError as e:
            assert "tenant" in str(e).lower()


def test_dependency_factory_returns_callable():
    from src.core.api.v1.feature_flags.dependencies import get_current_user_dep

    assert callable(get_current_user_dep())


def test_get_current_stats_returns_subscriptable_dict():
    from src.core.monitoring.performance_monitor import MetricsCollector

    collector = MetricsCollector()
    stats = collector.get_current_stats()
    assert isinstance(stats, dict)
    assert isinstance(stats["current"], dict)
    assert "cpu_percent" in stats["current"]


def test_get_cva_agent_returns_typed_object():
    from src.core.api.cva_admin import get_cva_agent

    mock_agent = AsyncMock()
    mock_agent.execution_history = []
    mock_provider = AsyncMock()
    mock_provider.get_or_create = AsyncMock(return_value=mock_agent)

    async def run():
        result = await get_cva_agent(tenant_id=1, cache_provider=mock_provider)
        assert result is mock_agent
        assert hasattr(result, "execution_history")

    asyncio.run(run())


def test_log_action_expects_a_numeric_tenant_id_or_none_never_text():
    """`tenant_id` is een getal of er is geen tenant, nooit tekst.

    Sinds e25f44af (SP-AUDIT-004) is de annotatie `int | None`: bij `None` slaat `log_action` de
    regel over en logt een waarschuwing. Eerder eiste deze test exact `int`; de kern (geen tekst)
    blijft hier overeind.
    """
    from src.core.governance.audit import AuditService

    sig = inspect.signature(AuditService.log_action)
    ann = sig.parameters["tenant_id"].annotation
    assert ann is int or ann == (int | None)


def test_data_category_enum_members_exist():
    from src.core.governance.retention_cleanup import DataCategory

    assert hasattr(DataCategory, "USER_DATA")
    assert hasattr(DataCategory, "ACTIVITY_LOGS")
    assert hasattr(DataCategory, "AI_INTERACTIONS")
    assert hasattr(DataCategory, "DOCUMENTS")
    assert hasattr(DataCategory, "ANALYTICS")


if __name__ == "__main__":
    tests = [
        test_tenant_id_raises_without_context,
        test_dependency_factory_returns_callable,
        test_get_current_stats_returns_subscriptable_dict,
        test_get_cva_agent_returns_typed_object,
        test_log_action_expects_a_numeric_tenant_id_or_none_never_text,
        test_data_category_enum_members_exist,
    ]
    for t in tests:
        try:
            t()
            print(f"{t.__name__}: PASS")
        except Exception as e:
            print(f"{t.__name__}: FAIL ({e})")
            sys.exit(1)
    print("\nALL UNIT TESTS PASSED")
