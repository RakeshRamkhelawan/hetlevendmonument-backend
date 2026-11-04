"""
Comprehensive tests for src/core/llm/llm_service.py
Coverage target: 100% of LLM service
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.core.llm.llm_client import LLMProvider
from src.core.llm.llm_service import LLMService

# ─── Module-level helpers ────────────────────────────────────────────────────


def _google_only_env(key: str, default=None):
    return {"GOOGLE_API_KEY": "test-api-key-123"}.get(key, default)


def _no_env(key: str, default=None):
    return default


@pytest.fixture(autouse=True)
def reset_singleton():
    LLMService._instance = None
    yield
    LLMService._instance = None


@pytest.fixture(autouse=True)
def disable_ollama():
    with patch(
        "src.core.llm.llm_service.OllamaProvider",
        side_effect=Exception("Ollama disabled in unit tests"),
    ):
        yield


# ─── TestLLMServiceInitialization ────────────────────────────────────────────


class TestLLMServiceInitialization:
    """Test LLMService initialization"""

    @pytest.mark.asyncio
    @patch("src.core.llm.llm_service.os.getenv")
    @patch("src.core.llm.llm_service.GeminiProvider")
    @patch("src.core.llm.llm_service.DeepSeekProvider", create=True)
    async def test_initialization_with_google_api_key(
        self, mock_deepseek, mock_gemini, mock_getenv
    ):
        """Test LLMService initializes with Google API key"""
        mock_getenv.side_effect = _google_only_env
        mock_provider = AsyncMock()
        mock_provider.initialized = True
        mock_provider.initialize = AsyncMock(return_value=True)
        mock_provider.model_names = ["gemini-1.5-flash"]
        mock_gemini.return_value = mock_provider
        mock_deepseek.side_effect = Exception("No DeepSeek key")

        service = LLMService()
        await service.initialize()

        assert LLMProvider.GOOGLE in service.providers
        assert service.default_provider == LLMProvider.GOOGLE

    @pytest.mark.asyncio
    @patch("src.core.llm.llm_service.os.getenv")
    @patch("src.core.llm.llm_service.GeminiProvider")
    @patch("src.core.llm.llm_service.DeepSeekProvider", create=True)
    async def test_initialization_without_api_key(self, mock_deepseek, mock_gemini, mock_getenv):
        """Test LLMService initialization without API key falls back to Mock"""
        mock_getenv.side_effect = _no_env
        mock_deepseek.side_effect = Exception("No key")
        mock_gemini.side_effect = Exception("No key")

        service = LLMService()
        await service.initialize()

        # Falls back to MockProvider
        assert LLMProvider.MOCK in service.providers

    @pytest.mark.asyncio
    @patch("src.core.llm.llm_service.os.getenv")
    @patch("src.core.llm.llm_service.GeminiProvider")
    @patch("src.core.llm.llm_service.DeepSeekProvider", create=True)
    async def test_initialization_provider_error(
        self, mock_deepseek, mock_gemini, mock_getenv, caplog
    ):
        """Test LLMService handles provider initialization errors"""
        import logging

        caplog.set_level(logging.ERROR)
        mock_getenv.side_effect = _google_only_env
        mock_gemini.side_effect = Exception("Provider init failed")
        mock_deepseek.side_effect = Exception("No key")

        service = LLMService()
        await service.initialize()

        # Provider failed, should not be in providers
        assert LLMProvider.GOOGLE not in service.providers


# ─── TestGenerateResponse ─────────────────────────────────────────────────────


class TestGenerateResponse:
    """Test LLMService.generate_response method"""

    @pytest.mark.asyncio
    @patch("src.core.llm.llm_service.os.getenv")
    @patch("src.core.llm.llm_service.GeminiProvider")
    @patch("src.core.llm.llm_service.DeepSeekProvider", create=True)
    async def test_generate_response_success(self, mock_deepseek, mock_gemini, mock_getenv):
        """Test successful response generation"""
        mock_getenv.side_effect = _google_only_env
        mock_provider = AsyncMock()
        mock_provider.initialized = True
        mock_provider.initialize = AsyncMock(return_value=True)
        mock_provider.generate_response = AsyncMock(
            return_value={"content": "Test response", "success": True}
        )
        mock_gemini.return_value = mock_provider
        mock_deepseek.side_effect = Exception("No key")

        service = LLMService()
        await service.initialize()
        result = await service.generate_response("Test prompt")

        assert result["content"] == "Test response"
        assert result["success"] is True
        assert "service_info" in result
        assert result["service_info"]["provider"] == "google"

    @pytest.mark.asyncio
    @patch("src.core.llm.llm_service.os.getenv")
    @patch("src.core.llm.llm_service.GeminiProvider")
    @patch("src.core.llm.llm_service.DeepSeekProvider", create=True)
    async def test_generate_response_with_custom_model(
        self, mock_deepseek, mock_gemini, mock_getenv
    ):
        """Test response generation with custom model"""
        mock_getenv.side_effect = _google_only_env
        mock_provider = AsyncMock()
        mock_provider.initialized = True
        mock_provider.initialize = AsyncMock(return_value=True)
        mock_provider.generate_response = AsyncMock(
            return_value={"content": "Custom model response", "success": True}
        )
        mock_gemini.return_value = mock_provider
        mock_deepseek.side_effect = Exception("No key")

        service = LLMService()
        await service.initialize()
        result = await service.generate_response("Test prompt", model="gemini-1.5-pro")

        mock_provider.generate_response.assert_called_once()
        call_kwargs = mock_provider.generate_response.call_args[1]
        assert call_kwargs["model"] == "gemini-1.5-pro"

    @pytest.mark.asyncio
    @patch("src.core.llm.llm_service.os.getenv")
    @patch("src.core.llm.llm_service.GeminiProvider")
    @patch("src.core.llm.llm_service.DeepSeekProvider", create=True)
    async def test_generate_response_with_tools(self, mock_deepseek, mock_gemini, mock_getenv):
        """Test response generation with function calling tools"""
        mock_getenv.side_effect = _google_only_env
        mock_provider = AsyncMock()
        mock_provider.initialized = True
        mock_provider.initialize = AsyncMock(return_value=True)
        mock_provider.generate_response = AsyncMock(
            return_value={"content": "Function call result", "success": True}
        )
        mock_gemini.return_value = mock_provider
        mock_deepseek.side_effect = Exception("No key")

        service = LLMService()
        await service.initialize()

        test_tool = Mock()
        result = await service.generate_response(
            "Test prompt", tools=[test_tool], automatic_function_calling=True
        )

        assert result["service_info"]["function_calling_enabled"] is True
        call_kwargs = mock_provider.generate_response.call_args[1]
        assert call_kwargs["tools"] == [test_tool]
        assert call_kwargs["automatic_function_calling"] is True

    @pytest.mark.asyncio
    @patch("src.core.llm.llm_service.os.getenv")
    @patch("src.core.llm.llm_service.GeminiProvider")
    @patch("src.core.llm.llm_service.DeepSeekProvider", create=True)
    async def test_generate_response_provider_error(self, mock_deepseek, mock_gemini, mock_getenv):
        """Test response generation handles provider errors"""
        mock_getenv.side_effect = _google_only_env
        mock_provider = AsyncMock()
        mock_provider.initialized = True
        mock_provider.initialize = AsyncMock(return_value=True)
        mock_provider.generate_response = AsyncMock(side_effect=Exception("Provider error"))
        mock_gemini.return_value = mock_provider
        mock_deepseek.side_effect = Exception("No key")

        from src.core.llm.llm_client import LLMServiceError

        service = LLMService()
        await service.initialize()
        with pytest.raises(LLMServiceError):
            await service.generate_response("Test prompt")

    @pytest.mark.asyncio
    @patch("src.core.llm.llm_service.os.getenv")
    @patch("src.core.llm.llm_service.GeminiProvider")
    @patch("src.core.llm.llm_service.DeepSeekProvider", create=True)
    async def test_generate_response_with_kwargs(self, mock_deepseek, mock_gemini, mock_getenv):
        """Test response generation passes kwargs to provider"""
        mock_getenv.side_effect = _google_only_env
        mock_provider = AsyncMock()
        mock_provider.initialized = True
        mock_provider.initialize = AsyncMock(return_value=True)
        mock_provider.generate_response = AsyncMock(
            return_value={"content": "Response", "success": True}
        )
        mock_gemini.return_value = mock_provider
        mock_deepseek.side_effect = Exception("No key")

        service = LLMService()
        await service.initialize()
        await service.generate_response("Test prompt", temperature=0.7, max_tokens=100)

        call_kwargs = mock_provider.generate_response.call_args[1]
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["max_tokens"] == 100


# ─── TestGetServiceStatus ─────────────────────────────────────────────────────


class TestGetServiceStatus:
    """Test LLMService.get_service_status method"""

    @pytest.mark.asyncio
    @patch("src.core.llm.llm_service.os.getenv")
    @patch("src.core.llm.llm_service.GeminiProvider")
    @patch("src.core.llm.llm_service.DeepSeekProvider", create=True)
    async def test_get_service_status_success(self, mock_deepseek, mock_gemini, mock_getenv):
        """Test successful service status retrieval"""
        mock_getenv.side_effect = _google_only_env
        mock_provider = AsyncMock()
        mock_provider.initialized = True
        mock_provider.initialize = AsyncMock(return_value=True)
        mock_provider.validate_connection = AsyncMock(
            return_value={"status": "ok", "available": True}
        )
        mock_gemini.return_value = mock_provider
        mock_deepseek.side_effect = Exception("No key")

        service = LLMService()
        await service.initialize()
        result = await service.get_service_status()

        assert result["service"] == "llm"
        assert result["default_provider"] == "google"
        assert result["total_providers"] == 1
        assert "google" in result["providers"]

    @pytest.mark.asyncio
    @patch("src.core.llm.llm_service.os.getenv")
    @patch("src.core.llm.llm_service.GeminiProvider")
    @patch("src.core.llm.llm_service.DeepSeekProvider", create=True)
    async def test_get_service_status_provider_error(self, mock_deepseek, mock_gemini, mock_getenv):
        """Test service status when provider validation fails"""
        mock_getenv.side_effect = _google_only_env
        mock_provider = AsyncMock()
        mock_provider.initialized = True
        mock_provider.initialize = AsyncMock(return_value=True)
        mock_provider.validate_connection = AsyncMock(side_effect=Exception("Connection failed"))
        mock_gemini.return_value = mock_provider
        mock_deepseek.side_effect = Exception("No key")

        service = LLMService()
        await service.initialize()
        result = await service.get_service_status()

        assert result["providers"]["google"]["status"] == "error"
        assert result["providers"]["google"]["available"] is False


# ─── TestTestConnectivity ─────────────────────────────────────────────────────


class TestTestConnectivity:
    """Test LLMService.test_connectivity method"""

    @pytest.mark.asyncio
    @patch("src.core.llm.llm_service.os.getenv")
    @patch("src.core.llm.llm_service.GeminiProvider")
    @patch("src.core.llm.llm_service.DeepSeekProvider", create=True)
    async def test_test_connectivity_success(self, mock_deepseek, mock_gemini, mock_getenv):
        """Test successful connectivity test"""
        mock_getenv.side_effect = _google_only_env
        mock_provider = AsyncMock()
        mock_provider.initialized = True
        mock_provider.initialize = AsyncMock(return_value=True)
        mock_provider.validate_connection = AsyncMock(
            return_value={"available": True, "status": "ok"}
        )
        mock_gemini.return_value = mock_provider
        mock_deepseek.side_effect = Exception("No key")

        service = LLMService()
        await service.initialize()
        result = await service.test_connectivity()

        assert result["total_tested"] == 1
        assert result["successful"] == 1
        assert result["failed"] == 0

    @pytest.mark.asyncio
    @patch("src.core.llm.llm_service.os.getenv")
    @patch("src.core.llm.llm_service.GeminiProvider")
    @patch("src.core.llm.llm_service.DeepSeekProvider", create=True)
    async def test_test_connectivity_failure(self, mock_deepseek, mock_gemini, mock_getenv):
        """Test connectivity test with failures"""
        mock_getenv.side_effect = _google_only_env
        mock_provider = AsyncMock()
        mock_provider.initialized = True
        mock_provider.initialize = AsyncMock(return_value=True)
        mock_provider.validate_connection = AsyncMock(side_effect=Exception("Connection error"))
        mock_gemini.return_value = mock_provider
        mock_deepseek.side_effect = Exception("No key")

        service = LLMService()
        await service.initialize()
        result = await service.test_connectivity()

        assert result["total_tested"] == 1
        assert result["successful"] == 0
        assert result["failed"] == 1


# ─── TestGetAvailableModels ───────────────────────────────────────────────────


class TestGetAvailableModels:
    """Test LLMService.get_available_models method"""

    @pytest.mark.asyncio
    @patch("src.core.llm.llm_service.os.getenv")
    @patch("src.core.llm.llm_service.GeminiProvider")
    @patch("src.core.llm.llm_service.DeepSeekProvider", create=True)
    async def test_get_available_models_for_provider(self, mock_deepseek, mock_gemini, mock_getenv):
        """Test getting models for specific provider"""
        mock_getenv.side_effect = _google_only_env
        mock_provider = AsyncMock()
        mock_provider.initialized = True
        mock_provider.initialize = AsyncMock(return_value=True)
        mock_provider.model_names = ["gemini-1.5-flash", "gemini-1.5-pro"]
        mock_gemini.return_value = mock_provider
        mock_deepseek.side_effect = Exception("No key")

        service = LLMService()
        await service.initialize()
        result = await service.get_available_models(LLMProvider.GOOGLE)

        assert "gemini-1.5-flash" in result
        assert "gemini-1.5-pro" in result

    @pytest.mark.asyncio
    @patch("src.core.llm.llm_service.os.getenv")
    @patch("src.core.llm.llm_service.GeminiProvider")
    @patch("src.core.llm.llm_service.DeepSeekProvider", create=True)
    async def test_get_available_models_all_providers(
        self, mock_deepseek, mock_gemini, mock_getenv
    ):
        """Test getting models from all providers"""
        mock_getenv.side_effect = _google_only_env
        mock_provider = AsyncMock()
        mock_provider.initialized = True
        mock_provider.initialize = AsyncMock(return_value=True)
        mock_provider.model_names = ["model-1", "model-2"]
        mock_gemini.return_value = mock_provider
        mock_deepseek.side_effect = Exception("No key")

        service = LLMService()
        await service.initialize()
        result = await service.get_available_models()

        assert "model-1" in result
        assert "model-2" in result

    @pytest.mark.asyncio
    @patch("src.core.llm.llm_service.os.getenv")
    @patch("src.core.llm.llm_service.GeminiProvider")
    @patch("src.core.llm.llm_service.DeepSeekProvider", create=True)
    async def test_get_available_models_no_providers(self, mock_deepseek, mock_gemini, mock_getenv):
        """Test getting models when no providers available"""
        mock_getenv.side_effect = _no_env
        mock_deepseek.side_effect = Exception("No key")
        mock_gemini.side_effect = Exception("No key")

        service = LLMService()
        await service.initialize()
        # Falls back to Mock provider; get_available_models() should still return list
        result = await service.get_available_models(LLMProvider.GOOGLE)

        assert isinstance(result, list)


# ─── TestIsProviderAvailable ──────────────────────────────────────────────────


class TestIsProviderAvailable:
    """Test LLMService.is_provider_available method"""

    @pytest.mark.asyncio
    @patch("src.core.llm.llm_service.os.getenv")
    @patch("src.core.llm.llm_service.GeminiProvider")
    @patch("src.core.llm.llm_service.DeepSeekProvider", create=True)
    async def test_is_provider_available_true(self, mock_deepseek, mock_gemini, mock_getenv):
        """Test provider availability check returns True"""
        mock_getenv.side_effect = _google_only_env
        mock_provider = AsyncMock()
        mock_provider.initialized = True
        mock_provider.initialize = AsyncMock(return_value=True)
        mock_gemini.return_value = mock_provider
        mock_deepseek.side_effect = Exception("No key")

        service = LLMService()
        await service.initialize()
        result = service.is_provider_available(LLMProvider.GOOGLE)

        assert result is True

    @pytest.mark.asyncio
    @patch("src.core.llm.llm_service.os.getenv")
    @patch("src.core.llm.llm_service.GeminiProvider")
    @patch("src.core.llm.llm_service.DeepSeekProvider", create=True)
    async def test_is_provider_available_false(self, mock_deepseek, mock_gemini, mock_getenv):
        """Test provider availability check returns False when not initialized"""
        mock_getenv.side_effect = _no_env
        mock_deepseek.side_effect = Exception("No key")
        mock_gemini.side_effect = Exception("No key")

        service = LLMService()
        await service.initialize()
        result = service.is_provider_available(LLMProvider.GOOGLE)

        assert result is False
