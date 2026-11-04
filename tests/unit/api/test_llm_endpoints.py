import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from src.core.api.llm_endpoints import router, get_available_models, get_llm_status


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/llm/models" in paths
    assert "/llm/status" in paths


@pytest.mark.asyncio
async def test_get_available_models_success() -> None:
    mock_model = MagicMock()
    mock_model.id = "model-1"
    mock_model.name = "GPT-4"
    mock_model.provider = "openai"
    mock_model.capabilities = ["chat", "code"]
    mock_model.description = "Test model"
    mock_model.context_window = 8192
    mock_model.max_output_tokens = 2048

    mock_service = MagicMock()
    mock_service.get_models_info.return_value = [mock_model]

    with patch("src.core.llm.llm_service.get_llm_service", AsyncMock(return_value=mock_service)):
        res = await get_available_models()
        assert len(res) == 1
        assert res[0].id == "model-1"
        assert res[0].name == "GPT-4"
        assert res[0].provider == "openai"


@pytest.mark.asyncio
async def test_get_available_models_error() -> None:
    with patch("src.core.llm.llm_service.get_llm_service", AsyncMock(side_effect=RuntimeError("LLM unavailable"))):
        with pytest.raises(HTTPException) as exc_info:
            await get_available_models()
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Er is een interne fout opgetreden."


@pytest.mark.asyncio
async def test_get_llm_status_success() -> None:
    mock_service = MagicMock()
    mock_service.test_connectivity = AsyncMock(return_value={"openai": {"status": "connected", "latency_ms": 42}})

    with patch("src.core.llm.llm_service.get_llm_service", AsyncMock(return_value=mock_service)):
        res = await get_llm_status()
        assert "openai" in res
        assert res["openai"]["status"] == "connected"


@pytest.mark.asyncio
async def test_get_llm_status_error() -> None:
    with patch("src.core.llm.llm_service.get_llm_service", AsyncMock(side_effect=RuntimeError("Provider failure"))):
        with pytest.raises(HTTPException) as exc_info:
            await get_llm_status()
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Er is een interne fout opgetreden."
