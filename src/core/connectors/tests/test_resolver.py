"""
Tests voor Provider Resolver

Happy paths:
- Primary provider available -> execute via primary
- Resolution volgens priority order
- Success metrics tracking

Unhappy paths:
- Primary down -> automatische fallback
- Alle providers falen -> controlled failure
- Circuit open -> skip provider
- Disabled provider -> skip
"""

import asyncio

import pytest

from src.core.connectors.circuit_breaker import CircuitBreakerConfig
from src.core.connectors.provider import MockEmailProvider, MockSMSProvider, ProviderCapability
from src.core.connectors.resolver import ProviderPriority, ProviderResolver, ResolutionResult


class TestProviderResolver:
    """Test provider resolver basis functionaliteit."""

    @pytest.fixture
    def resolver(self):
        return ProviderResolver(tenant_id="test-tenant")

    @pytest.fixture
    def email_providers(self):
        """Create email providers met verschillende failure rates."""
        primary = MockEmailProvider("email_primary", failure_rate=0.0)
        fallback = MockEmailProvider("email_fallback", failure_rate=0.0)
        return primary, fallback

    def test_register_provider(self, resolver, email_providers):
        """Happy path: Provider registratie."""
        primary, _ = email_providers

        resolver.register_provider(primary, priority=1)

        assert "email_primary" in resolver._providers
        assert "email_primary" in resolver._circuit_breakers

    def test_register_with_capabilities(self, resolver):
        """Happy path: Provider met specifieke capabilities."""
        provider = MockEmailProvider("email1")

        resolver.register_provider(
            provider,
            priority=1,
            capabilities=[ProviderCapability.EMAIL_SEND],
        )

        # Alleen EMAIL_SEND geregistreerd, niet EMAIL_BATCH
        caps = resolver._priorities.get(ProviderCapability.EMAIL_SEND, [])
        assert any(p.provider_id == "email1" for p in caps)

    @pytest.mark.asyncio
    async def test_resolve_success(self, resolver, email_providers):
        """Happy path: Primary provider slaagt."""
        primary, fallback = email_providers

        resolver.register_provider(primary, priority=1)
        resolver.register_provider(fallback, priority=2)

        result = await resolver.resolve_and_execute(
            capability=ProviderCapability.EMAIL_SEND,
            payload={"to": "test@test.com", "subject": "Test", "body": "Hello"},
        )

        assert result.success is True
        assert result.provider_id == "email_primary"
        assert result.fallback_used is False

    @pytest.mark.asyncio
    async def test_resolve_fallback(self, resolver):
        """Happy path: Fallback gebruikt als primary faalt."""
        failing = MockEmailProvider("failing", failure_rate=1.0)  # Altijd falen
        fallback = MockEmailProvider("fallback", failure_rate=0.0)

        resolver.register_provider(failing, priority=1)
        resolver.register_provider(fallback, priority=2)

        result = await resolver.resolve_and_execute(
            capability=ProviderCapability.EMAIL_SEND,
            payload={"to": "test@test.com", "subject": "Test", "body": "Hello"},
        )

        assert result.success is True
        assert result.provider_id == "fallback"
        assert result.fallback_used is True
        assert result.fallback_from == "failing"

    @pytest.mark.asyncio
    async def test_resolve_all_fail(self, resolver):
        """Unhappy path: Alle providers falen."""
        failing1 = MockEmailProvider("fail1", failure_rate=1.0)
        failing2 = MockEmailProvider("fail2", failure_rate=1.0)

        resolver.register_provider(failing1, priority=1)
        resolver.register_provider(failing2, priority=2)

        result = await resolver.resolve_and_execute(
            capability=ProviderCapability.EMAIL_SEND,
            payload={"to": "test@test.com", "subject": "Test", "body": "Hello"},
        )

        assert result.success is False
        assert result.provider_id is None
        assert len(result.attempts) == 2  # Beide geprobeerd

    @pytest.mark.asyncio
    async def test_circuit_open_skips_provider(self, resolver):
        """Unhappy path: Circuit open -> provider wordt overgeslagen."""
        provider = MockEmailProvider("unhealthy", failure_rate=1.0)

        resolver.register_provider(provider, priority=1)

        # Open circuit door failures
        cb = resolver.get_circuit_breaker("unhealthy")
        for _ in range(5):
            cb.record_failure("Error")

        assert cb.state.value == "open"

        # Nu zou de provider overgeslagen moeten worden
        result = await resolver.resolve_and_execute(
            capability=ProviderCapability.EMAIL_SEND,
            payload={"to": "test@test.com", "subject": "Test", "body": "Hello"},
        )

        assert result.success is False
        # Circuit was open, dus provider werd overgeslagen
        assert any(a.get("skipped") and a.get("reason") == "circuit_open" for a in result.attempts)


class TestProviderPriority:
    """Test provider priority ordering."""

    @pytest.mark.asyncio
    async def test_priority_order(self):
        """Happy path: Providers worden in priority order gebruikt."""
        resolver = ProviderResolver(tenant_id="test")

        # Register in verkeerde volgorde
        p3 = MockEmailProvider("p3")
        p1 = MockEmailProvider("p1")
        p2 = MockEmailProvider("p2")

        resolver.register_provider(p3, priority=3)
        resolver.register_provider(p1, priority=1)
        resolver.register_provider(p2, priority=2)

        result = await resolver.resolve_and_execute(
            capability=ProviderCapability.EMAIL_SEND,
            payload={"to": "test@test.com", "subject": "Test", "body": "Hello"},
        )

        # p1 heeft priority 1 (hoogste), dus die zou gebruikt moeten worden
        assert result.success is True
        assert result.provider_id == "p1"

    def test_set_provider_priority(self):
        """Happy path: Priority lijst instellen."""
        resolver = ProviderResolver(tenant_id="test")

        p1 = MockEmailProvider("p1")
        p2 = MockEmailProvider("p2")

        resolver.register_provider(p1)
        resolver.register_provider(p2)

        # Set custom priorities
        resolver.set_provider_priority(
            ProviderCapability.EMAIL_SEND,
            [
                ProviderPriority("p2", priority=1),  # p2 eerst
                ProviderPriority("p1", priority=2),
            ],
        )

        priorities = resolver._priorities[ProviderCapability.EMAIL_SEND]
        assert priorities[0].provider_id == "p2"
        assert priorities[1].provider_id == "p1"


class TestResolverMetrics:
    """Test resolver metrics."""

    @pytest.mark.asyncio
    async def test_fallback_counting(self):
        """Happy path: Fallbacks worden geteld."""
        resolver = ProviderResolver(tenant_id="test")

        failing = MockEmailProvider("fail", failure_rate=1.0)
        fallback = MockEmailProvider("fallback", failure_rate=0.0)

        resolver.register_provider(failing, priority=1)
        resolver.register_provider(fallback, priority=2)

        # Eerste call met fallback
        await resolver.resolve_and_execute(
            capability=ProviderCapability.EMAIL_SEND,
            payload={"to": "test@test.com", "subject": "Test", "body": "Hello"},
        )

        # Tweede call met fallback
        await resolver.resolve_and_execute(
            capability=ProviderCapability.EMAIL_SEND,
            payload={"to": "test@test.com", "subject": "Test 2", "body": "Hello"},
        )

        metrics = resolver.get_metrics()

        assert metrics["resolution_count"] == 2
        assert metrics["fallback_count"] == 2
        assert metrics["fallback_rate"] == 1.0

    def test_circuit_breaker_stats(self):
        """Happy path: Circuit breaker stats ophalen."""
        resolver = ProviderResolver(tenant_id="test")

        provider = MockEmailProvider("testprovider")
        resolver.register_provider(provider)

        stats = resolver.get_all_circuit_breaker_stats()

        # Check dat er stats zijn voor de provider
        assert len(stats) >= 1
        # Key bevat provider name
        matching_keys = [k for k in stats.keys() if "testprovider" in k]
        assert len(matching_keys) >= 1
        assert stats[matching_keys[0]]["state"] == "closed"


class TestMaxAttempts:
    """Test max attempts limiting."""

    @pytest.mark.asyncio
    async def test_max_attempts_limit(self):
        """Happy path: Max attempts limiet werkt."""
        resolver = ProviderResolver(tenant_id="test")

        # Register 3 failing providers
        for i in range(3):
            resolver.register_provider(
                MockEmailProvider(f"fail{i}", failure_rate=1.0),
                priority=i + 1,
            )

        # Alleen 2 proberen (max_attempts=2)
        result = await resolver.resolve_and_execute(
            capability=ProviderCapability.EMAIL_SEND,
            payload={"to": "test@test.com", "subject": "Test", "body": "Hello"},
            max_attempts=2,
        )

        assert result.success is False
        assert len(result.attempts) == 2  # Max 2 attempts
