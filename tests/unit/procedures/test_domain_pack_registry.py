"""
Slice 2: Unit tests for DomainPackRegistry (RED → GREEN → REFACTOR)
Tests the active pack retrieval, tenant isolation, and tag-based procedure search

Test cases:
- test_get_active_packs: Return only packs with status='active'
- test_cross_tenant_isolation: Prevent access to other tenants' packs
- test_find_candidates_by_tag: Tag-based procedure matching
- test_caching_strategy: 5-minute cache TTL
- test_empty_results: Handle no matching procedures
- test_concurrent_access: Thread-safe caching

NOTE (2026-08-01): deze suite gebruikte `uuid4()`-tenants. Dat is een fictie: alle 21
`tenant_id`-kolommen in de modellen zijn `Mapped[int]`, `DomainPackRepository.list_by_tenant`
neemt een int, en beide productie-aanroepers (de health-check en department_service) geven
een int. De UUID's bereikten de echte kolom nooit omdat deze tests tegen een GEMOCKTE
repository draaien -- een UUID-tenant zou tegen een echte repository stil nul rijen
opleveren. De tenants zijn daarom ints; pack-id's blijven UUID (DomainPack.id IS een UUID).
Afgedwongen door tests/architecture/test_tenant_id_type_matches_model.py.
"""

from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.procedures.domain_pack_registry import DomainPackRegistry
from src.core.procedures.schemas import DomainPackRead


class TestGetActivePacks:
    """Test retrieval of active domain packs"""

    @pytest.mark.asyncio
    async def test_get_active_packs_returns_only_active_status(self):
        """
        Given: Repository with mixed status packs (active, deprecated, archived)
        When: get_active_packs() is called
        Then: Must return ONLY packs with status='active'
        """
        # Arrange
        tenant_id = 1
        registry = DomainPackRegistry(db_manager=MagicMock())

        mock_packs = [
            {
                "id": str(uuid4()),
                "name": "Finance Active",
                "status": "active",
                "tenant_id": str(tenant_id),
            },
            {
                "id": str(uuid4()),
                "name": "Finance Deprecated",
                "status": "deprecated",
                "tenant_id": str(tenant_id),
            },
            {
                "id": str(uuid4()),
                "name": "Finance Archived",
                "status": "archived",
                "tenant_id": str(tenant_id),
            },
        ]

        with patch.object(registry, "_repository") as mock_repo:
            mock_repo.get_domain_packs_by_tenant = AsyncMock(return_value=mock_packs)

            # Act
            result = await registry.get_active_packs(tenant_id)

            # Assert
            assert len(result) == 1
            assert result[0]["status"] == "active"
            assert result[0]["name"] == "Finance Active"

    @pytest.mark.asyncio
    async def test_get_active_packs_empty_on_no_active(self):
        """
        Given: Repository with NO active packs
        When: get_active_packs() is called
        Then: Must return empty list, not error
        """
        # Arrange
        tenant_id = 1
        registry = DomainPackRegistry(db_manager=MagicMock())

        mock_packs = [
            {
                "id": str(uuid4()),
                "name": "Pack 1",
                "status": "deprecated",
                "tenant_id": str(tenant_id),
            },
            {
                "id": str(uuid4()),
                "name": "Pack 2",
                "status": "archived",
                "tenant_id": str(tenant_id),
            },
        ]

        with patch.object(registry, "_repository") as mock_repo:
            mock_repo.get_domain_packs_by_tenant = AsyncMock(return_value=mock_packs)

            # Act
            result = await registry.get_active_packs(tenant_id)

            # Assert
            assert result == []


class TestCrossTenantIsolation:
    """Test tenant isolation enforcement"""

    @pytest.mark.asyncio
    async def test_cross_tenant_isolation_prevents_access_to_other_tenant_packs(self):
        """
        Given: Repository with packs from multiple tenants
        When: get_active_packs() is called with tenant_id A
        Then: Must NEVER return packs from tenant_id B
        """
        # Arrange
        tenant_a = 1
        tenant_b = 2
        registry = DomainPackRegistry(db_manager=MagicMock())

        # Simulate DB returning all packs (registry must filter)
        all_packs = [
            {
                "id": str(uuid4()),
                "name": "Tenant A Pack",
                "status": "active",
                "tenant_id": str(tenant_a),
            },
            {
                "id": str(uuid4()),
                "name": "Tenant B Pack",
                "status": "active",
                "tenant_id": str(tenant_b),
            },
        ]

        with patch.object(registry, "_repository") as mock_repo:
            # Repository should be called with tenant_id filter
            async def filtered_get(tenant_id):
                return [p for p in all_packs if p["tenant_id"] == str(tenant_id)]

            mock_repo.get_domain_packs_by_tenant = AsyncMock(side_effect=filtered_get)

            # Act
            result_a = await registry.get_active_packs(tenant_a)
            result_b = await registry.get_active_packs(tenant_b)

            # Assert
            assert len(result_a) == 1
            assert result_a[0]["tenant_id"] == str(tenant_a)

            assert len(result_b) == 1
            assert result_b[0]["tenant_id"] == str(tenant_b)

            # Critical: results must be completely separate
            assert result_a[0]["id"] != result_b[0]["id"]


class TestFindCandidatesByTag:
    """Test tag-based procedure discovery"""

    @pytest.mark.asyncio
    async def test_find_candidates_by_tag_matches_procedure_tags(self):
        """
        Given: Procedures with various intent_tags
        When: find_candidates_by_tag(intent, domain_filter) is called
        Then: Must return procedures where intent matches any tag
        """
        # Arrange
        tenant_id = 1
        registry = DomainPackRegistry(db_manager=MagicMock())

        procedures = [
            {
                "id": str(uuid4()),
                "name": "Invoice Approval",
                "intent_tags": ["invoice", "approval", "finance"],
                "category": "finance",
                "domain_pack_id": str(uuid4()),
            },
            {
                "id": str(uuid4()),
                "name": "Payment Request",
                "intent_tags": ["payment", "request", "finance"],
                "category": "finance",
                "domain_pack_id": str(uuid4()),
            },
            {
                "id": str(uuid4()),
                "name": "Leave Request",
                "intent_tags": ["leave", "request", "hr"],
                "category": "hr",
                "domain_pack_id": str(uuid4()),
            },
        ]

        with patch.object(registry, "_repository") as mock_repo:
            mock_repo.get_procedures_by_tenant = AsyncMock(return_value=procedures)

            # Act
            # Search for "approval" - should find Invoice Approval
            result = await registry.find_candidates_by_tag(
                intent="Approve invoice",  # Will be parsed for keywords
                tenant_id=tenant_id,
                domain_filter=None,
            )

            # Assert
            assert len(result) > 0
            # At least one procedure should have matching tag
            matching_found = any("approval" in p["intent_tags"] for p in result)
            assert matching_found, "Should find procedures with matching tags"

    @pytest.mark.asyncio
    async def test_find_candidates_with_domain_filter(self):
        """
        Given: Multiple domain packs (finance, hr, legal)
        When: find_candidates_by_tag(intent, domain_filter="finance") is called
        Then: Must return only finance procedures
        """
        # Arrange
        tenant_id = 1
        registry = DomainPackRegistry(db_manager=MagicMock())

        procedures = [
            {
                "id": str(uuid4()),
                "intent_tags": ["invoice"],
                "category": "finance",
                "domain_pack_id": str(uuid4()),
            },
            {
                "id": str(uuid4()),
                "intent_tags": ["payroll"],
                "category": "finance",
                "domain_pack_id": str(uuid4()),
            },
            {
                "id": str(uuid4()),
                "intent_tags": ["leave"],
                "category": "hr",
                "domain_pack_id": str(uuid4()),
            },
        ]

        with patch.object(registry, "_repository") as mock_repo:
            mock_repo.get_procedures_by_tenant = AsyncMock(return_value=procedures)

            # Act
            result = await registry.find_candidates_by_tag(
                intent="invoice", tenant_id=tenant_id, domain_filter="finance"
            )

            # Assert
            # All results should be from finance domain
            for proc in result:
                assert proc["category"] == "finance"


class TestCachingStrategy:
    """Test 5-minute cache TTL"""

    @pytest.mark.asyncio
    async def test_caching_strategy_returns_cached_result_within_ttl(self):
        """
        Given: Registry with caching enabled
        When: Same query called twice within 5 minutes
        Then: Second call must return cached result (repository not called)
        """
        # Arrange
        tenant_id = 1
        registry = DomainPackRegistry(db_manager=MagicMock())

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

            # Act - First call
            result1 = await registry.get_active_packs(tenant_id)
            call_count_1 = mock_repo.get_domain_packs_by_tenant.call_count

            # Second call (should use cache)
            result2 = await registry.get_active_packs(tenant_id)
            call_count_2 = mock_repo.get_domain_packs_by_tenant.call_count

            # Assert
            assert result1 == result2
            # Repository should only be called once (second call uses cache)
            assert call_count_1 == 1
            assert call_count_2 == 1

    @pytest.mark.asyncio
    async def test_cache_timeout_expires_after_ttl(self):
        """
        Given: Cached result
        When: More than 5 minutes pass
        Then: Cache expires and repository is called again
        """
        # Arrange
        tenant_id = 1
        registry = DomainPackRegistry(
            cache_ttl_minutes=0.001
        )  # 0.001 minutes = very short for testing

        mock_packs_v1 = [
            {
                "id": str(uuid4()),
                "name": "Pack V1",
                "status": "active",
                "tenant_id": str(tenant_id),
            }
        ]
        mock_packs_v2 = [
            {
                "id": str(uuid4()),
                "name": "Pack V2",
                "status": "active",
                "tenant_id": str(tenant_id),
            }
        ]

        with patch.object(registry, "_repository") as mock_repo:
            mock_repo.get_domain_packs_by_tenant = AsyncMock(
                side_effect=[mock_packs_v1, mock_packs_v2]
            )

            # Act - First call
            result1 = await registry.get_active_packs(tenant_id)

            # Wait for cache to expire (simulated)
            import asyncio

            await asyncio.sleep(0.1)

            # Second call (cache expired)
            result2 = await registry.get_active_packs(tenant_id)

            # Assert
            assert result1[0]["name"] == "Pack V1"
            assert result2[0]["name"] == "Pack V2"
            # Repository should be called twice
            assert mock_repo.get_domain_packs_by_tenant.call_count == 2


class TestEmptyResults:
    """Test handling of empty or no-match scenarios"""

    @pytest.mark.asyncio
    async def test_empty_results_returns_empty_list_not_error(self):
        """
        Given: Query with no matching results
        When: find_candidates_by_tag() is called
        Then: Must return empty list, not error
        """
        # Arrange
        tenant_id = 1
        registry = DomainPackRegistry(db_manager=MagicMock())

        with patch.object(registry, "_repository") as mock_repo:
            mock_repo.get_procedures_by_tenant = AsyncMock(return_value=[])

            # Act
            result = await registry.find_candidates_by_tag(
                intent="nonexistent procedure", tenant_id=tenant_id, domain_filter=None
            )

            # Assert
            assert result == []

    @pytest.mark.asyncio
    async def test_no_active_packs_handles_gracefully(self):
        """
        Given: Tenant with no active domain packs
        When: get_active_packs() is called
        Then: Must return empty list, log warning, not crash
        """
        # Arrange
        tenant_id = 1
        registry = DomainPackRegistry(db_manager=MagicMock())

        with patch.object(registry, "_repository") as mock_repo:
            mock_repo.get_domain_packs_by_tenant = AsyncMock(return_value=[])

            # Act
            result = await registry.get_active_packs(tenant_id)

            # Assert
            assert result == []


class TestErrorHandling:
    """Test error resilience"""

    @pytest.mark.asyncio
    async def test_repository_failure_raises_error(self):
        """
        Given: Repository fails with exception
        When: get_active_packs() is called
        Then: Error should be raised (no silent fail)
        """
        # Arrange
        tenant_id = 1
        registry = DomainPackRegistry(db_manager=MagicMock())

        with patch.object(registry, "_repository") as mock_repo:
            mock_repo.get_domain_packs_by_tenant = AsyncMock(
                side_effect=Exception("Database connection failed")
            )

            # Act & Assert
            with pytest.raises(Exception) as exc_info:
                await registry.get_active_packs(tenant_id)

            assert "Database connection failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalid_tenant_id_raises_error(self):
        """
        Given: Invalid tenant_id (None or empty)
        When: get_active_packs() is called
        Then: Must raise validation error
        """
        # Arrange
        registry = DomainPackRegistry(db_manager=MagicMock())

        # Act & Assert
        with pytest.raises((ValueError, TypeError)):
            await registry.get_active_packs(None)


class TestPerformance:
    """Test performance characteristics"""

    @pytest.mark.asyncio
    async def test_large_result_set_handling(self):
        """
        Given: 1000+ procedures to search
        When: find_candidates_by_tag() is called
        Then: Must complete in reasonable time and not crash
        """
        # Arrange
        tenant_id = 1
        registry = DomainPackRegistry(db_manager=MagicMock())

        # Generate large result set
        large_procedure_set = [
            {
                "id": str(uuid4()),
                "name": f"Procedure {i}",
                "intent_tags": ["test", "large", "dataset"],
                "category": "finance",
                "domain_pack_id": str(uuid4()),
            }
            for i in range(1000)
        ]

        with patch.object(registry, "_repository") as mock_repo:
            mock_repo.get_procedures_by_tenant = AsyncMock(return_value=large_procedure_set)

            # Act
            import time

            start = time.time()
            result = await registry.find_candidates_by_tag(
                intent="large", tenant_id=tenant_id, domain_filter=None
            )
            elapsed = time.time() - start

            # Assert
            assert len(result) == 1000
            assert elapsed < 5.0, f"Search took {elapsed}s, should be <5s"
