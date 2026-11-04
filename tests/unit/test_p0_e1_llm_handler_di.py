"""
AUDIT-P0-E1: LLMHandler must receive LLMClient, not LLMProviderFactory instance.

RED phase: test_build_copilot_service_passes_llm_client_to_handler will FAIL
until dependencies.py is fixed (LLMProviderFactory() -> LLMProviderFactory.get_provider()).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
class TestLLMHandlerDependencyInjection:
    """LLMHandler must receive an LLMClient, never a factory object."""

    def test_llm_provider_factory_instance_is_not_llm_client(self):
        """Documents the bug: LLMProviderFactory() is NOT an LLMClient."""
        from src.core.llm.provider_factory import LLMProviderFactory
        from src.core.llm.llm_client import LLMClient

        factory_instance = LLMProviderFactory()
        assert not isinstance(factory_instance, LLMClient), (
            "LLMProviderFactory() should not be an LLMClient — "
            "passing it to LLMHandler is the bug (AUDIT-P0-E1)"
        )

    def test_llm_provider_factory_get_provider_returns_llm_client(self):
        """get_provider() classmethod must return an LLMClient."""
        from src.core.llm.llm_client import LLMClient
        from src.core.llm.provider_factory import LLMProviderFactory

        mock_client = MagicMock(spec=LLMClient)
        mock_provider_class = MagicMock(return_value=mock_client)

        with patch(
            "src.core.llm.provider_registry.ProviderRegistry.get", return_value=mock_provider_class
        ):
            LLMProviderFactory.reset()
            provider = LLMProviderFactory.get_provider(provider_type="gemini")
            assert isinstance(provider, LLMClient), (
                "LLMProviderFactory.get_provider() must return an LLMClient instance"
            )

    def test_llm_handler_init_accepts_llm_client(self):
        """LLMHandler.__init__ type annotation requires LLMClient, not factory."""
        import inspect
        from src.core.copilot.llm_handler import LLMHandler
        from src.core.llm.llm_client import LLMClient

        sig = inspect.signature(LLMHandler.__init__)
        provider_param = sig.parameters.get("provider")
        assert provider_param is not None
        assert provider_param.annotation is LLMClient or str(provider_param.annotation) in (
            "LLMClient",
            "src.core.llm.llm_client.LLMClient",
            "JsonModel",  # protocol: een provider OF het model van de tenant (brief 2026-10-19)
        ), "LLMHandler.__init__ must have provider: LLMClient annotation"

    def test_build_copilot_service_passes_llm_client_to_handler(self):
        """
        RED: LLMHandler._provider must be an LLMClient after _build_copilot_service().
        This test FAILS before the fix because LLMProviderFactory() is passed.
        """
        import asyncio
        from src.core.llm.llm_client import LLMClient
        from src.core.llm.provider_factory import LLMProviderFactory

        # Simulate what _build_copilot_service does
        mock_provider = MagicMock(spec=LLMClient)

        with patch.object(LLMProviderFactory, "get_provider", return_value=mock_provider):
            from src.core.copilot.llm_handler import LLMHandler

            # After fix: LLMHandler should receive mock_provider (an LLMClient)
            handler = LLMHandler(mock_provider)
            assert isinstance(handler._provider, LLMClient), (
                "LLMHandler._provider must be an LLMClient, not a factory object"
            )
            assert handler._provider is mock_provider
