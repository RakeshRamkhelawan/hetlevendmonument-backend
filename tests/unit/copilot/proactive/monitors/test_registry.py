"""Unit tests for InMemoryHealthMonitorRegistry."""

from __future__ import annotations

import pytest

from src.core.als.health_monitor import HealthMonitorService
from src.core.als.registry import InMemoryHealthMonitorRegistry


@pytest.mark.unit
class TestInMemoryHealthMonitorRegistry:
    def test_get_for_tenant_returns_none_when_empty(self) -> None:
        registry = InMemoryHealthMonitorRegistry()
        assert registry.get_for_tenant(1) is None

    def test_register_and_retrieve(self) -> None:
        registry = InMemoryHealthMonitorRegistry()
        service = HealthMonitorService()
        registry.register(1, service)
        assert registry.get_for_tenant(1) is service

    def test_different_tenants_isolated(self) -> None:
        registry = InMemoryHealthMonitorRegistry()
        service_a = HealthMonitorService()
        service_b = HealthMonitorService()
        registry.register(1, service_a)
        registry.register(2, service_b)
        assert registry.get_for_tenant(1) is service_a
        assert registry.get_for_tenant(2) is service_b

    def test_overwrite_existing(self) -> None:
        registry = InMemoryHealthMonitorRegistry()
        service1 = HealthMonitorService()
        service2 = HealthMonitorService()
        registry.register(1, service1)
        registry.register(1, service2)
        assert registry.get_for_tenant(1) is service2

    def test_register_multiple_tenants_and_list(self) -> None:
        registry = InMemoryHealthMonitorRegistry()
        registry.register(1, HealthMonitorService())
        registry.register(2, HealthMonitorService())
        registry.register(3, HealthMonitorService())
        assert registry.get_for_tenant(1) is not None
        assert registry.get_for_tenant(2) is not None
        assert registry.get_for_tenant(3) is not None
        assert registry.get_for_tenant(4) is None
