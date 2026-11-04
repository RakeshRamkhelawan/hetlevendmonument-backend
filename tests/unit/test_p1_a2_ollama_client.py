"""
AUDIT-P1-A2: OllamaClient.complete_json() ontbreekt.

RED PHASE: De base-class implementatie raise NotImplementedError.
Callers mogen geen exception krijgen -- ze verwachten LLMResponse(success=False).

GREEN PHASE: OllamaClient overschrijft complete_json en retourneert
LLMResponse(success=False, error_message=...) zonder exception te gooien.
"""

import pytest


@pytest.mark.unit
class TestOllamaClientCompleteJson:
    @pytest.mark.asyncio
    async def test_complete_json_returns_llm_response_not_exception(self):
        """
        AUDIT-P1-A2: OllamaClient.complete_json() moet LLMResponse(success=False)
        retourneren, niet NotImplementedError gooien.

        Root cause: base-class complete_json() raise NotImplementedError.
        OllamaClient overschrijft hem niet -- callers crashen onverwacht.
        """
        from src.core.llm.llm_client import (
            LLMConfig,
            LLMMessage,
            LLMModel,
            LLMProvider,
            OllamaClient,
        )

        config = LLMConfig(
            provider=LLMProvider.OLLAMA,
            model=LLMModel.LLAMA_3,
            api_key="",
        )
        client = OllamaClient(config)

        result = await client.complete_json(
            messages=[LLMMessage(role="user", content="t")],
            schema=dict,
        )

        assert result.success is False, (
            "AUDIT-P1-A2: complete_json() moet success=False retourneren, niet een exception gooien"
        )
        assert result.error_message is not None, (
            "AUDIT-P1-A2: error_message moet aanwezig zijn zodat caller "
            "begrijpt waarom JSON-mode niet beschikbaar is"
        )
