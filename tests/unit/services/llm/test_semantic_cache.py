from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.services.llm.base import LLMMessage, LLMResponse
from src.core.services.llm.service import LLMService


@pytest.mark.asyncio
async def test_semantic_cache_full_flow():
    """
    Test de volledige flow: Miss -> LLM -> Cache Set -> Get -> Hit.
    """
    # 1. Mock Provider
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = LLMResponse(
        content="Parijs", model="gemini", prompt_tokens=10, completion_tokens=2, total_tokens=12
    )
    mock_provider.provider_name = "google"
    mock_provider.config = MagicMock(model="gemini")

    # 2. Mock SemanticCache
    # We willen testen of LLMService de cache correct aanroept
    with (
        patch(
            "src.core.services.llm.factory.ProviderFactory.create_from_env",
            return_value=mock_provider,
        ),
        patch("src.core.services.llm.cache.SemanticCache.get") as mock_get,
        patch("src.core.services.llm.cache.SemanticCache.set") as mock_set,
    ):
        mock_get.side_effect = [None, "Parijs"]  # Eerst miss, dan hit
        mock_set.return_value = None

        service = LLMService(enable_cache=True)
        messages = [{"role": "user", "content": "Hoofdstad Frankrijk?"}]
        tenant_id = 1

        # --- RUN 1: MISS ---
        res1, usage1 = await service.generate(messages, tenant_id=tenant_id, return_usage=True)

        assert res1 == "Parijs"
        assert usage1["total_tokens"] == 12
        assert mock_provider.generate.call_count == 1
        assert mock_set.call_count == 1

        # --- RUN 2: HIT ---
        res2, usage2 = await service.generate(messages, tenant_id=tenant_id, return_usage=True)

        assert res2 == "Parijs"
        assert usage2["total_tokens"] == 0
        assert usage2["model"] == "cache"
        # Provider count mag nog steeds 1 zijn!
        assert mock_provider.generate.call_count == 1

        print("\n✅ TDD: LLMService <-> SemanticCache integratie geslaagd.")


@pytest.mark.asyncio
async def test_cache_disabled_skips_logic():
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = LLMResponse(
        content="Hi", model="m", prompt_tokens=1, completion_tokens=1, total_tokens=2
    )
    mock_provider.provider_name = "p"
    mock_provider.config = MagicMock(model="m")

    with (
        patch(
            "src.core.services.llm.factory.ProviderFactory.create_from_env",
            return_value=mock_provider,
        ),
        patch("src.core.services.llm.cache.SemanticCache.get") as mock_get,
    ):
        service = LLMService(enable_cache=False)
        await service.generate([{"role": "user", "content": "Hi"}], tenant_id=1)

        # Cache get mag NIET zijn aangeroepen
        assert mock_get.call_count == 0
