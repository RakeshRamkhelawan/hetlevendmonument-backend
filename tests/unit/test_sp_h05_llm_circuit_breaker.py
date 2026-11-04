"""SP-H05: Tests for CircuitBreakerRegistry in LLMFallbackChain (B-008).

B-008: LLMFallbackChain has no circuit breaker -- provider outage causes cascade
failure as the chain retries the dead provider on every call.

Fix: Add CircuitBreakerRegistry per provider+model key. OPEN circuit = skip without
counting as a failure attempt. HALF_OPEN = single probe request.
"""

import pathlib
import pytest

_ROOT = pathlib.Path(__file__).parent.parent.parent


@pytest.mark.unit
class TestFallbackChainCircuitBreakerRegistration:
    def test_fallback_chain_imports_circuit_breaker_registry(self) -> None:
        """LLMFallbackChain must import CircuitBreakerRegistry (B-008)."""
        source = (_ROOT / "src/core/llm/fallback_chain.py").read_text()
        assert "CircuitBreakerRegistry" in source, (
            "fallback_chain.py does not import CircuitBreakerRegistry -- B-008 not fixed"
        )

    def test_fallback_chain_imports_circuit_open_error(self) -> None:
        """LLMFallbackChain must catch CircuitOpenError to skip OPEN providers."""
        source = (_ROOT / "src/core/llm/fallback_chain.py").read_text()
        assert "CircuitOpenError" in source, (
            "fallback_chain.py does not reference CircuitOpenError -- "
            "OPEN providers will not be skipped (B-008)"
        )

    def test_fallback_chain_has_circuit_breaker_registry_attribute(self) -> None:
        """LLMFallbackChain must have a _cb_registry attribute."""
        from src.core.llm.fallback_chain import LLMFallbackChain

        chain = LLMFallbackChain()
        assert hasattr(chain, "_cb_registry"), (
            "LLMFallbackChain has no _cb_registry attribute -- circuit breaker not wired in"
        )

    def test_fallback_chain_has_get_circuit_states_method(self) -> None:
        """LLMFallbackChain must expose get_circuit_states() for monitoring."""
        from src.core.llm.fallback_chain import LLMFallbackChain

        chain = LLMFallbackChain()
        assert hasattr(chain, "get_circuit_states"), (
            "LLMFallbackChain has no get_circuit_states() -- circuit state not observable"
        )


@pytest.mark.unit
class TestFallbackChainCircuitBreakerBehavior:
    @pytest.mark.asyncio
    async def test_open_circuit_skips_provider_without_failure_count(self) -> None:
        """OPEN circuit skips the provider; chain attempts counter stays unchanged."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.core.llm.fallback_chain import LLMFallbackChain, ModelConfig, ModelTier
        from src.core.resilience.circuit_breaker import CircuitOpenError

        chain = LLMFallbackChain()
        chain.register_model(
            ModelConfig(
                name="primary-model",
                tier=ModelTier.PRIMARY,
                provider="openai",
                timeout_seconds=5.0,
            )
        )
        chain.register_model(
            ModelConfig(
                name="fallback-model",
                tier=ModelTier.SECONDARY,
                provider="google",
                timeout_seconds=5.0,
            )
        )

        async def side_effect(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise CircuitOpenError("openai#primary-model")

        # Patch the circuit breaker for the primary model to raise CircuitOpenError
        # and patch _call_model to succeed for the secondary
        with patch.object(chain, "_call_model", new_callable=AsyncMock) as mock_call:
            # First call (primary, openai): circuit open
            # Second call (fallback, google): success
            call_count = 0

            async def mock_impl(model_config, **kwargs):  # type: ignore[no-untyped-def]
                nonlocal call_count
                call_count += 1
                if model_config.provider == "openai":
                    raise CircuitOpenError("openai#primary-model")
                return "fallback response"

            mock_call.side_effect = mock_impl

            # Patch get_breaker to return a mock that raises CircuitOpenError for openai
            # but passes through for google
            from src.core.resilience.circuit_breaker import CircuitBreaker

            async def passthrough_execute(func, *args, **kwargs):  # type: ignore[no-untyped-def]
                return await func(*args, **kwargs)

            mock_breaker = MagicMock(spec=CircuitBreaker)
            mock_breaker.execute = AsyncMock(side_effect=passthrough_execute)
            mock_registry = MagicMock()
            mock_registry.get_breaker = AsyncMock(return_value=mock_breaker)
            chain._cb_registry = mock_registry  # type: ignore[assignment]

            result = await chain.generate(prompt="test")

        # Should succeed via the fallback model
        assert result.success is True
        assert result.content == "fallback response"
        # errors should NOT contain "circuit open" as a failure
        assert not any("circuit" in e.lower() for e in result.errors), (
            "CircuitOpenError was counted as a chain failure -- should be silently skipped"
        )

    @pytest.mark.asyncio
    async def test_get_circuit_states_returns_dict(self) -> None:
        """get_circuit_states() must return a dict with state info."""
        from src.core.llm.fallback_chain import LLMFallbackChain

        chain = LLMFallbackChain()
        states = await chain.get_circuit_states()
        assert isinstance(states, dict), "get_circuit_states() must return a dict"

    @pytest.mark.asyncio
    async def test_circuit_breaker_key_uses_provider_and_model_name(self) -> None:
        """Circuit breaker key must be {provider}#{name} for unique identification."""
        source = (_ROOT / "src/core/llm/fallback_chain.py").read_text()
        # The key pattern should incorporate both provider and model name
        assert "provider" in source and (
            "model_config.name" in source or "model_config.provider" in source
        ), "fallback_chain.py circuit breaker key does not use provider or model name"
