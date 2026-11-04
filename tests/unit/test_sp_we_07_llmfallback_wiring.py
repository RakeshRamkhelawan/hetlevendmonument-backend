"""SP-WE-07: LLMHandler failover via CircuitBreakerRegistry tests."""

import inspect

import pytest
from unittest.mock import AsyncMock, MagicMock


def _make_raw(
    success: bool = True,
    content: str = '{"message":"hello","action":null,"action_params":{},"confidence":0.9,"reasoning":"ok"}',
) -> MagicMock:
    r = MagicMock()
    r.success = success
    r.content = content
    r.error_message = None if success else "provider error"
    return r


@pytest.mark.unit
class TestLLMHandlerFallbackProviders:
    def test_llm_handler_accepts_fallback_providers(self) -> None:
        """LLMHandler constructor accepts fallback_providers list."""
        from src.core.copilot.llm_handler import LLMHandler

        sig = inspect.signature(LLMHandler.__init__)
        assert "fallback_providers" in sig.parameters

    def test_llm_handler_backward_compat_single_provider(self) -> None:
        """LLMHandler(provider=p) still works without fallback_providers."""
        from src.core.copilot.llm_handler import LLMHandler

        primary = MagicMock()
        handler = LLMHandler(provider=primary)
        assert handler._provider is primary

    def test_raw_success_guard_present(self) -> None:
        """raw.success guard still present (SP-H03 must not be removed)."""
        from src.core.copilot.llm_handler import LLMHandler

        source = inspect.getsource(LLMHandler.get_action)
        assert "raw.success" in source

    async def test_primary_provider_used_on_success(self) -> None:
        """Primary provider is called first."""
        from src.core.copilot.llm_handler import LLMHandler

        primary = AsyncMock()
        primary.complete_json = AsyncMock(return_value=_make_raw())
        handler = LLMHandler(provider=primary)

        result = await handler.get_action(message="hello", context={}, language="nl")
        assert primary.complete_json.called
        assert result is not None

    async def test_fallback_used_when_primary_fails(self) -> None:
        """Fallback provider used when primary raises LLMProviderError."""
        from src.core.copilot.llm_handler import LLMHandler, LLMProviderError
        from src.core.resilience.circuit_breaker import CircuitBreakerRegistry

        primary = AsyncMock()
        primary.complete_json = AsyncMock(return_value=_make_raw(success=False))

        fallback = AsyncMock()
        fallback.complete_json = AsyncMock(return_value=_make_raw(success=True))

        handler = LLMHandler(
            provider=primary,
            fallback_providers=[fallback],
            circuit_breaker_registry=CircuitBreakerRegistry(),
        )

        result = await handler.get_action(message="hello", context={}, language="nl")
        assert fallback.complete_json.called
        assert result is not None

    async def test_all_providers_fail_raises_llm_provider_error(self) -> None:
        """All providers fail -> LLMProviderError raised."""
        from src.core.copilot.llm_handler import LLMHandler, LLMProviderError
        from src.core.resilience.circuit_breaker import CircuitBreakerRegistry

        primary = AsyncMock()
        primary.complete_json = AsyncMock(return_value=_make_raw(success=False))
        fallback = AsyncMock()
        fallback.complete_json = AsyncMock(return_value=_make_raw(success=False))

        handler = LLMHandler(
            provider=primary,
            fallback_providers=[fallback],
            circuit_breaker_registry=CircuitBreakerRegistry(),
        )

        with pytest.raises(LLMProviderError):
            await handler.get_action(message="hello", context={}, language="nl")

    def test_dependencies_references_fallback(self) -> None:
        """dependencies.py references fallback_providers or CircuitBreakerRegistry."""
        import src.core.copilot.dependencies as deps

        source = inspect.getsource(deps)
        assert "fallback" in source.lower() or "CircuitBreakerRegistry" in source
