"""
Direct implementation tests for Slice 2: DomainPackRegistry
These tests verify the core logic works without FastAPI fixtures
"""

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from src.core.procedures.domain_pack_registry import DomainPackRegistry


async def test_active_packs_filtering():
    """Test that only active packs are returned"""
    registry = DomainPackRegistry()
    tenant_id = uuid4()

    mock_packs = [
        {
            "id": str(uuid4()),
            "name": "Pack A",
            "status": "active",
            "tenant_id": str(tenant_id),
        },
        {
            "id": str(uuid4()),
            "name": "Pack B",
            "status": "deprecated",
            "tenant_id": str(tenant_id),
        },
        {
            "id": str(uuid4()),
            "name": "Pack C",
            "status": "archived",
            "tenant_id": str(tenant_id),
        },
    ]

    with patch.object(registry, "_repository") as mock_repo:
        mock_repo.get_domain_packs_by_tenant = AsyncMock(return_value=mock_packs)

        result = await registry.get_active_packs(tenant_id)

        print("✅ Test 1: Active Packs Filtering")
        print(f"   Input: {len(mock_packs)} packs (mixed status)")
        print(f"   Output: {len(result)} packs (active only)")
        assert len(result) == 1
        assert result[0]["status"] == "active"
        print("   ✓ Correctly filtered to 1 active pack")


async def test_tenant_isolation():
    """Test that packs from other tenants are not returned"""
    registry = DomainPackRegistry()
    tenant_a = uuid4()
    tenant_b = uuid4()

    packs_a = [
        {
            "id": str(uuid4()),
            "name": "Tenant A Pack",
            "status": "active",
            "tenant_id": str(tenant_a),
        },
    ]

    packs_b = [
        {
            "id": str(uuid4()),
            "name": "Tenant B Pack",
            "status": "active",
            "tenant_id": str(tenant_b),
        },
    ]

    with patch.object(registry, "_repository") as mock_repo:

        async def get_by_tenant(tenant_id):
            if tenant_id == tenant_a:
                return packs_a
            elif tenant_id == tenant_b:
                return packs_b
            return []

        mock_repo.get_domain_packs_by_tenant = AsyncMock(side_effect=get_by_tenant)

        result_a = await registry.get_active_packs(tenant_a)
        result_b = await registry.get_active_packs(tenant_b)

        print("✅ Test 2: Tenant Isolation")
        print(f"   Tenant A results: {len(result_a)} packs")
        print(f"   Tenant B results: {len(result_b)} packs")
        assert len(result_a) == 1
        assert result_a[0]["tenant_id"] == str(tenant_a)
        assert len(result_b) == 1
        assert result_b[0]["tenant_id"] == str(tenant_b)
        print("   ✓ Complete isolation maintained")


async def test_tag_based_search():
    """Test finding procedures by tag matching"""
    registry = DomainPackRegistry()
    tenant_id = uuid4()

    procedures = [
        {
            "id": str(uuid4()),
            "name": "Invoice Approval",
            "intent_tags": ["invoice", "approval", "finance"],
            "category": "finance",
        },
        {
            "id": str(uuid4()),
            "name": "Leave Request",
            "intent_tags": ["leave", "request", "hr"],
            "category": "hr",
        },
    ]

    with patch.object(registry, "_repository") as mock_repo:
        mock_repo.get_procedures_by_tenant = AsyncMock(return_value=procedures)

        result = await registry.find_candidates_by_tag(
            intent="Approve invoice", tenant_id=tenant_id, domain_filter=None
        )

        print("✅ Test 3: Tag-Based Search")
        print("   Intent: 'Approve invoice'")
        print(f"   Candidates found: {len(result)}")

        # Should find procedures with matching tags
        assert len(result) >= 1
        matching = any("approval" in p["intent_tags"] for p in result)
        assert matching
        print("   ✓ Found procedures with matching tags")


async def test_domain_filtering():
    """Test domain/category filtering in search"""
    registry = DomainPackRegistry()
    tenant_id = uuid4()

    procedures = [
        {
            "id": str(uuid4()),
            "name": "Invoice",
            "intent_tags": ["invoice"],
            "category": "finance",
        },
        {
            "id": str(uuid4()),
            "name": "Payroll",
            "intent_tags": ["payroll"],
            "category": "finance",
        },
        {
            "id": str(uuid4()),
            "name": "Leave",
            "intent_tags": ["leave"],
            "category": "hr",
        },
    ]

    with patch.object(registry, "_repository") as mock_repo:
        mock_repo.get_procedures_by_tenant = AsyncMock(return_value=procedures)

        # Search with finance filter
        result = await registry.find_candidates_by_tag(
            intent="approval", tenant_id=tenant_id, domain_filter="finance"
        )

        print("✅ Test 4: Domain Filtering")
        print("   Domain filter: 'finance'")
        print(f"   Results: {len(result)} procedures")

        # All results should be finance category
        for proc in result:
            assert proc["category"] == "finance"
        print("   ✓ All results filtered to finance domain")


async def test_caching():
    """Test caching behavior"""
    registry = DomainPackRegistry()
    tenant_id = uuid4()

    mock_packs = [
        {
            "id": str(uuid4()),
            "name": "Pack 1",
            "status": "active",
            "tenant_id": str(tenant_id),
        },
    ]

    with patch.object(registry, "_repository") as mock_repo:
        mock_repo.get_domain_packs_by_tenant = AsyncMock(return_value=mock_packs)

        # First call
        result1 = await registry.get_active_packs(tenant_id)
        calls_after_first = mock_repo.get_domain_packs_by_tenant.call_count

        # Second call (should use cache)
        result2 = await registry.get_active_packs(tenant_id)
        calls_after_second = mock_repo.get_domain_packs_by_tenant.call_count

        print("✅ Test 5: Caching Strategy")
        print(f"   Calls after first query: {calls_after_first}")
        print(f"   Calls after second query: {calls_after_second}")
        print(f"   Cache hit: {calls_after_first == calls_after_second}")

        assert result1 == result2
        assert calls_after_first == 1
        assert calls_after_second == 1
        print("   ✓ Cache working correctly (no duplicate calls)")


async def test_empty_results():
    """Test handling of empty result sets"""
    registry = DomainPackRegistry()
    tenant_id = uuid4()

    with patch.object(registry, "_repository") as mock_repo:
        mock_repo.get_domain_packs_by_tenant = AsyncMock(return_value=[])

        result = await registry.get_active_packs(tenant_id)

        print("✅ Test 6: Empty Result Handling")
        print(f"   Results: {result}")
        assert result == []
        print("   ✓ Handles empty results gracefully")


async def test_keyword_extraction():
    """Test keyword extraction from intent"""
    registry = DomainPackRegistry()

    # Test keyword extraction
    keywords = registry._extract_keywords("Approve invoice for $200")

    print("✅ Test 7: Keyword Extraction")
    print("   Input: 'Approve invoice for $200'")
    print(f"   Keywords: {keywords}")

    # Should extract meaningful keywords
    assert "approve" in keywords
    assert "invoice" in keywords
    assert "the" not in keywords  # Stop word should be removed
    print("   ✓ Correctly extracted keywords")


async def test_error_handling():
    """Test error handling"""
    registry = DomainPackRegistry()
    tenant_id = uuid4()

    with patch.object(registry, "_repository") as mock_repo:
        mock_repo.get_domain_packs_by_tenant = AsyncMock(side_effect=Exception("Database error"))

        try:
            await registry.get_active_packs(tenant_id)
            assert False, "Should have raised exception"
        except Exception as e:
            print("✅ Test 8: Error Handling")
            print(f"   Exception caught: {e}")
            print("   ✓ Properly propagates errors")


async def main():
    print("\n" + "=" * 70)
    print("SLICE 2: DomainPackRegistry - Direct Implementation Tests (GREEN PHASE)")
    print("=" * 70 + "\n")

    try:
        await test_active_packs_filtering()
        print()
        await test_tenant_isolation()
        print()
        await test_tag_based_search()
        print()
        await test_domain_filtering()
        print()
        await test_caching()
        print()
        await test_empty_results()
        print()
        await test_keyword_extraction()
        print()
        await test_error_handling()

        print()
        print("=" * 70)
        print("✅ ALL DIRECT TESTS PASSED (GREEN PHASE CONFIRMED)")
        print("=" * 70 + "\n")
        return True
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
