"""
Sprint 3 Slice 3: Domain Packs API - Direct Tests
Quick validation without pytest fixtures
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4


async def test_stats_endpoint():
    """Test overall stats calculation"""
    print("Testing stats endpoint logic...")

    from src.core.observability.evaluation_repository import EvaluationRepository

    # Mock database session
    mock_db = AsyncMock()

    # Mock execute results - scalar() should return actual values, not coroutines
    mock_result_1 = MagicMock()
    mock_result_1.scalar.return_value = 5  # total_packs

    mock_result_2 = MagicMock()
    mock_result_2.scalar.return_value = 4  # active_packs

    mock_result_3 = MagicMock()
    mock_result_3.scalar.return_value = 12  # total_procedures

    mock_db.execute.side_effect = [mock_result_1, mock_result_2, mock_result_3]

    repo = EvaluationRepository(mock_db)
    tenant_id = uuid4()

    stats = await repo.get_overall_stats(tenant_id)

    assert "total_packs" in stats
    assert "active_packs" in stats
    assert "total_procedures" in stats
    assert stats["total_packs"] == 5
    assert stats["active_packs"] == 4
    assert stats["total_procedures"] == 12

    print("✓ Stats endpoint logic working")
    return True


async def test_pack_stats_calculation():
    """Test individual pack stats"""
    print("Testing pack stats calculation...")

    from src.core.observability.evaluation_repository import EvaluationRepository

    mock_db = AsyncMock()

    # Mock results: procedure_count=3, executions_count=100, failed_count=15
    mock_result_1 = MagicMock()
    mock_result_1.scalar.return_value = 3

    mock_result_2 = MagicMock()
    mock_result_2.scalar.return_value = 100

    mock_result_3 = MagicMock()
    mock_result_3.scalar.return_value = 15

    mock_db.execute.side_effect = [mock_result_1, mock_result_2, mock_result_3]

    repo = EvaluationRepository(mock_db)
    pack_id = uuid4()
    tenant_id = uuid4()

    stats = await repo.get_pack_stats(pack_id, tenant_id, days=30)

    assert "procedure_count" in stats
    assert stats["procedure_count"] == 3
    assert "executions_30d" in stats
    assert stats["executions_30d"] == 100
    assert "failure_rate" in stats
    assert stats["failure_rate"] == 15.0  # 15/100 * 100

    print("✓ Pack stats calculation working")
    return True


async def test_health_check_logic():
    """Test health status determination"""
    print("Testing health check logic...")

    from src.core.observability.evaluation_repository import EvaluationRepository

    mock_db = AsyncMock()

    # Scenario 1: Healthy pack (low failure rate)
    # procedure_count=5, executions=50, failed=2 → 4% failure rate
    mock_results = [
        MagicMock(scalar=MagicMock(return_value=5)),
        MagicMock(scalar=MagicMock(return_value=50)),
        MagicMock(scalar=MagicMock(return_value=2)),
    ]
    mock_db.execute.side_effect = mock_results

    repo = EvaluationRepository(mock_db)
    pack_id = uuid4()
    tenant_id = uuid4()

    health = await repo.get_pack_health(pack_id, tenant_id)

    assert "status" in health
    assert health["status"] in ["healthy", "degraded", "unhealthy"]
    assert "violations" in health
    assert isinstance(health["violations"], list)

    print("✓ Health check logic working")
    return True


async def test_health_degraded_on_high_failure():
    """Test degraded status for high failure rate"""
    print("Testing degraded status detection...")

    from src.core.observability.evaluation_repository import EvaluationRepository

    mock_db = AsyncMock()

    # High failure rate: 30/100 = 30%
    mock_results = [
        MagicMock(scalar=MagicMock(return_value=5)),
        MagicMock(scalar=MagicMock(return_value=100)),
        MagicMock(scalar=MagicMock(return_value=30)),
    ]
    mock_db.execute.side_effect = mock_results

    repo = EvaluationRepository(mock_db)
    pack_id = uuid4()
    tenant_id = uuid4()

    health = await repo.get_pack_health(pack_id, tenant_id)

    assert health["status"] == "degraded"
    assert len(health["violations"]) > 0
    assert any(v["type"] == "elevated_failure_rate" for v in health["violations"])

    print("✓ Degraded status detected for high failure rate")
    return True


async def test_health_unhealthy_on_critical_failure():
    """Test unhealthy status for critical failure rate"""
    print("Testing unhealthy status detection...")

    from src.core.observability.evaluation_repository import EvaluationRepository

    mock_db = AsyncMock()

    # Critical failure rate: 60/100 = 60%
    mock_results = [
        MagicMock(scalar=MagicMock(return_value=5)),
        MagicMock(scalar=MagicMock(return_value=100)),
        MagicMock(scalar=MagicMock(return_value=60)),
    ]
    mock_db.execute.side_effect = mock_results

    repo = EvaluationRepository(mock_db)
    pack_id = uuid4()
    tenant_id = uuid4()

    health = await repo.get_pack_health(pack_id, tenant_id)

    assert health["status"] == "unhealthy"
    assert any(v["severity"] == "critical" for v in health["violations"])
    assert any(v["type"] == "high_failure_rate" for v in health["violations"])

    print("✓ Unhealthy status detected for critical failure rate")
    return True


async def test_health_warning_no_procedures():
    """Test warning for pack with no procedures"""
    print("Testing no-procedures warning...")

    from src.core.observability.evaluation_repository import EvaluationRepository

    mock_db = AsyncMock()

    # Pack with 0 procedures
    mock_results = [
        MagicMock(scalar=MagicMock(return_value=0)),
        MagicMock(scalar=MagicMock(return_value=0)),
        MagicMock(scalar=MagicMock(return_value=0)),
    ]
    mock_db.execute.side_effect = mock_results

    repo = EvaluationRepository(mock_db)
    pack_id = uuid4()
    tenant_id = uuid4()

    health = await repo.get_pack_health(pack_id, tenant_id)

    assert any(v["type"] == "no_procedures" for v in health["violations"])

    print("✓ No-procedures warning detected")
    return True


async def test_api_imports():
    """Test that API module imports correctly"""
    print("Testing API imports...")

    try:
        from src.core.api.domain_packs import router

        assert router is not None
        assert router.prefix == "/api/v1/domain-packs"

        # Check new endpoints are registered
        routes = [route.path for route in router.routes]
        print(f"  Found {len(routes)} routes: {routes}")

        # Check if new endpoints exist (more flexible matching)
        has_stats = any("stats" in route for route in routes)
        has_health = any("health" in route for route in routes)
        has_restore = any("restore" in route for route in routes)

        assert has_stats, "Stats endpoint not found"
        assert has_health, "Health endpoint not found"
        assert has_restore, "Restore endpoint not found"

        print("✓ API imports and routes registered")
        return True
    except Exception as e:
        print(f"✗ Import error: {type(e).__name__}: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run all direct tests"""
    print("\nSprint 3 Slice 3: Domain Packs API - Direct Tests")
    print("=" * 60)

    tests = [
        test_stats_endpoint,
        test_pack_stats_calculation,
        test_health_check_logic,
        test_health_degraded_on_high_failure,
        test_health_unhealthy_on_critical_failure,
        test_health_warning_no_procedures,
        test_api_imports,
    ]

    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"✗ Test failed: {e}")
            import traceback

            traceback.print_exc()
            results.append(False)

    print("\n" + "=" * 60)
    print(f"Results: {sum(results)}/{len(results)} tests passed")

    if all(results):
        print("✅ All direct tests passing!")
        return True
    else:
        print("❌ Some tests failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
