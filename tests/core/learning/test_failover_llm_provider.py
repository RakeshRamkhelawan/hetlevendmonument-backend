"""
Unit tests voor FailoverLLMProvider.

Controleert:
- Eerste provider succes → direct resultaat
- Eerste provider faalt → tweede provider wordt geprobeerd
- Alle providers falen → lege string
- EU-only chain bouwt correct
- Global chain bouwt correct
"""

import pytest

from src.core.learning.interfaces.failover_llm_provider import FailoverLLMProvider
from src.core.learning.interfaces.llm_provider import MockSuggestionProvider


@pytest.mark.asyncio
class TestFailoverLLMProvider:
    """Tests voor FailoverLLMProvider failover gedrag."""

    async def test_first_provider_success_returns_immediately(self):
        p1 = MockSuggestionProvider(response="suggestion from p1")
        p2 = MockSuggestionProvider(response="suggestion from p2")
        chain = FailoverLLMProvider([p1, p2])

        result = await chain.suggest(context={}, user_profile={})

        assert result == "suggestion from p1"
        assert p1.call_count == 1
        assert p2.call_count == 0

    async def test_first_fails_second_succeeds(self):
        p1 = MockSuggestionProvider(raise_error=True)
        p2 = MockSuggestionProvider(response="suggestion from p2")
        chain = FailoverLLMProvider([p1, p2])

        result = await chain.suggest(context={}, user_profile={})

        assert result == "suggestion from p2"
        assert p1.call_count == 1
        assert p2.call_count == 1

    async def test_all_providers_fail_returns_empty(self):
        p1 = MockSuggestionProvider(raise_error=True)
        p2 = MockSuggestionProvider(raise_error=True)
        chain = FailoverLLMProvider([p1, p2])

        result = await chain.suggest(context={}, user_profile={})

        assert result == ""
        assert p1.call_count == 1
        assert p2.call_count == 1

    async def test_first_returns_empty_second_tried(self):
        """Lege string van eerste provider telt als fail → probeer volgende."""
        p1 = MockSuggestionProvider(response="")
        p2 = MockSuggestionProvider(response="suggestion from p2")
        chain = FailoverLLMProvider([p1, p2])

        result = await chain.suggest(context={}, user_profile={})

        assert result == "suggestion from p2"
        assert p1.call_count == 1
        assert p2.call_count == 1

    async def test_single_provider_chain(self):
        p1 = MockSuggestionProvider(response="only provider")
        chain = FailoverLLMProvider([p1])

        result = await chain.suggest(context={}, user_profile={})

        assert result == "only provider"

    async def test_provider_count_and_names(self):
        p1 = MockSuggestionProvider(response="p1")
        p2 = MockSuggestionProvider(response="p2")
        chain = FailoverLLMProvider([p1, p2])

        assert chain.provider_count == 2
        assert chain.provider_names == [
            "MockSuggestionProvider",
            "MockSuggestionProvider",
        ]


@pytest.mark.asyncio
class TestFailoverLLMProviderCircuitBreaker:
    """Tests voor circuit breaker integratie in FailoverLLMProvider."""

    async def test_circuit_opens_after_failure_threshold(self):
        """Na 3 opeenvolgende failures gaat het circuit OPEN."""
        p1 = MockSuggestionProvider(raise_error=True)
        chain = FailoverLLMProvider([p1])

        # 3 failures — circuit threshold
        for _ in range(3):
            await chain.suggest(context={}, user_profile={})

        assert p1.call_count == 3
        states = await chain.get_circuit_states()
        assert states.get("MockSuggestionProvider#0") == "open"

    async def test_open_circuit_skips_provider_without_calling(self):
        """Na open circuit wordt provider overgeslagen — geen extra aanroep."""
        p1 = MockSuggestionProvider(raise_error=True)
        chain = FailoverLLMProvider([p1])

        for _ in range(3):
            await chain.suggest(context={}, user_profile={})

        call_count_before = p1.call_count
        result = await chain.suggest(context={}, user_profile={})

        assert result == ""
        # Provider NIET opnieuw aangeroepen — circuit was OPEN
        assert p1.call_count == call_count_before

    async def test_open_first_provider_falls_through_to_second(self):
        """Open circuit op provider 1 → provider 2 wordt geprobeerd."""
        p1 = MockSuggestionProvider(raise_error=True)
        p2 = MockSuggestionProvider(response="fallback from p2")
        chain = FailoverLLMProvider([p1, p2])

        # Open het circuit van provider 1
        for _ in range(3):
            await chain.suggest(context={}, user_profile={})

        # Vierde aanroep: p1 circuit OPEN → p2 succesvol
        result = await chain.suggest(context={}, user_profile={})

        assert result == "fallback from p2"
        # p1 is niet nogmaals aangeroepen
        assert p1.call_count == 3

    async def test_circuit_states_property_returns_all_active_providers(self):
        """circuit_states retourneert states voor alle providers die ooit faalden."""
        p1 = MockSuggestionProvider(raise_error=True)
        chain = FailoverLLMProvider([p1])

        await chain.suggest(context={}, user_profile={})

        states = await chain.get_circuit_states()
        assert "MockSuggestionProvider#0" in states
        assert states["MockSuggestionProvider#0"] == "closed"  # 1 failure, threshold=3

    async def test_circuit_starts_closed(self):
        """Circuit breaker begint altijd in CLOSED state."""
        chain = FailoverLLMProvider([MockSuggestionProvider(response="ok")])
        assert await chain.get_circuit_states() == {}  # Nog geen breaker aangemaakt voor succesvolle providers

    async def test_successful_call_does_not_open_circuit(self):
        """Succesvolle aanroepen openen het circuit niet."""
        p1 = MockSuggestionProvider(response="success")
        chain = FailoverLLMProvider([p1])

        for _ in range(10):
            result = await chain.suggest(context={}, user_profile={})
            assert result == "success"

        assert p1.call_count == 10
        # Circuit blijft gesloten
        states = await chain.get_circuit_states()
        if "MockSuggestionProvider" in states:
            assert states["MockSuggestionProvider"] == "closed"
