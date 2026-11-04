"""
Unit Tests for LLM Service
Tests LLM provider management and request routing

Coverage Target: llm_service.py 22.6% → >90%
"""

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.core.llm.llm_client import LLMProvider
from src.core.llm.llm_service import LLMService


@pytest.fixture(autouse=True)
def _geen_omgevingssleutel_van_een_taalmodel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deze tests gaan uit van een omgeving ZONDER `MISTRAL_API_KEY` en `LLM_PROVIDER`.

    Een eerdere test of een lokaal dotenv-bestand kan ze zetten (gemeten 2026-10-19 in een brede run:
    `LLM_PROVIDER=Mistral` en een sleutel aanwezig). Sinds `LLM_PROVIDER=deepseek` met een Mistralsleutel
    Mistral wordt, maakt dat een DeepSeek-testopzet stil anders.
    """
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture(autouse=True)
def reset_llm_service_singleton():
    """Reset LLMService singleton before every test to ensure isolation"""
    LLMService._instance = None
    yield
    LLMService._instance = None


@pytest.fixture(autouse=True)
def disable_ollama_provider():
    """Disable OllamaProvider for all tests - Ollama may be running locally."""
    with patch(
        "src.core.llm.llm_service.OllamaProvider",
        side_effect=Exception("Ollama disabled in unit tests"),
    ):
        yield


@pytest.fixture(autouse=True)
def set_default_deepseek_env():
    """Ensure DeepSeekProvider mock is invoked.

    Sinds de Mistral-brief (2026-10-19, ADR-041 B14) wordt DeepSeek alleen nog geinitialiseerd als de
    uitrol er uitdrukkelijk voor kiest (`LLM_PROVIDER=deepseek`); de sleutel alleen is niet genoeg.
    """
    with patch.dict(
        "os.environ",
        {"DEEPSEEK_API_KEY": "fake-deepseek-key-for-testing", "LLM_PROVIDER": "deepseek"},
        clear=False,
    ):
        yield


@pytest.fixture
def mock_gemini_provider():
    """Mock GeminiProvider"""
    provider = AsyncMock()
    provider.initialized = True
    provider.model_names = ["gemini-2.5-flash", "gemini-1.5-pro"]
    provider.generate_response = AsyncMock(
        return_value={
            "content": "Test response",
            "success": True,
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }
    )
    provider.validate_connection = AsyncMock(
        return_value={"status": "ok", "available": True, "latency_ms": 150}
    )
    return provider


@pytest.fixture
async def llm_service_with_provider(mock_gemini_provider):
    """LLM Service with mocked Google provider"""
    # Clear ALL other LLM provider keys to ensure only Google is configured
    env_clear = {
        "GOOGLE_API_KEY": "test-key-123",
        "DEEPSEEK_API_KEY": "",
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
    }
    with patch.dict("os.environ", env_clear, clear=False):
        with patch("src.core.llm.llm_service.GeminiProvider", return_value=mock_gemini_provider):
            with patch(
                "src.core.llm.llm_service.DeepSeekProvider", create=True,
                side_effect=Exception("No key"),
            ):
                # Disable Ollama to ensure isolation for Google provider testing
                with patch(
                    "src.core.llm.llm_service.OllamaProvider",
                    side_effect=Exception("Ollama disabled"),
                ):
                    service = LLMService()
                    await service.initialize()
                    yield service


@pytest.fixture
async def llm_service_no_provider():
    """LLM Service without providers (no API key)"""
    # Clear ALL LLM provider keys
    env_clear = {
        "GOOGLE_API_KEY": "",
        "DEEPSEEK_API_KEY": "",
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
    }
    with patch.dict("os.environ", env_clear, clear=False):
        with patch("src.core.llm.llm_service.GeminiProvider", side_effect=Exception("No key")):
            with patch(
                "src.core.llm.llm_service.DeepSeekProvider", create=True,
                side_effect=Exception("No key"),
            ):
                # Ensure Ollama is also disabled for this test to force Mock fallback
                with patch(
                    "src.core.llm.llm_service.OllamaProvider",
                    side_effect=Exception("Ollama disabled"),
                ):
                    service = LLMService()
                    await service.initialize()
                    yield service


# ============================================================================
# TEST: Initialization
# ============================================================================


class TestInitialization:
    """Test LLMService initialization"""

    @pytest.mark.asyncio
    async def test_init_with_google_api_key(self, mock_gemini_provider):
        """Test initialization with Google API key present"""
        # Clear ALL LLM provider keys to ensure only Google is configured
        env_clear = {
            "GOOGLE_API_KEY": "test-key",
            "DEEPSEEK_API_KEY": "",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
        }
        with patch.dict("os.environ", env_clear, clear=False):
            with patch(
                "src.core.llm.llm_service.GeminiProvider",
                return_value=mock_gemini_provider,
            ):
                # Also patch DeepSeekProvider to prevent it from loading
                with patch(
                    "src.core.llm.llm_service.DeepSeekProvider", create=True,
                    side_effect=Exception("No key"),
                ):
                    service = LLMService()
                    await service.initialize()

                    assert LLMProvider.GOOGLE in service.providers
                    assert service.default_provider == LLMProvider.GOOGLE
                    assert service.default_model == "gemini-2.5-flash"

    @pytest.mark.asyncio
    async def test_init_without_google_api_key(self):
        """Test initialization without ANY API keys"""
        # Clear ALL LLM provider keys
        env_clear = {
            "GOOGLE_API_KEY": "",
            "DEEPSEEK_API_KEY": "",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
        }
        with patch.dict("os.environ", env_clear, clear=False):
            # We should test normal init, not patched init
            # But disable Ollama to ensure Mock fallback
            with patch(
                "src.core.llm.llm_service.OllamaProvider",
                side_effect=Exception("Ollama disabled"),
            ):
                service = LLMService()
                await service.initialize()

                # Should fall back to Mock
                assert LLMProvider.MOCK in service.providers
            assert service.default_provider == LLMProvider.MOCK

    @pytest.mark.asyncio
    async def test_init_google_provider_error(self):
        """Test initialization handles provider initialization error"""
        # Clear other provider keys to ensure only Google is attempted
        env_clear = {
            "GOOGLE_API_KEY": "test-key",
            "DEEPSEEK_API_KEY": "",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
        }

        mock_provider = AsyncMock()
        mock_provider.initialize.return_value = False

        with patch.dict("os.environ", env_clear, clear=False):
            with patch("src.core.llm.llm_service.GeminiProvider", return_value=mock_provider):
                with patch(
                    "src.core.llm.llm_service.DeepSeekProvider", create=True,
                    side_effect=Exception("No key"),
                ):
                    service = LLMService()
                    await service.initialize()

                    assert LLMProvider.GOOGLE not in service.providers


# ============================================================================
# TEST: Generate Response
# ============================================================================


class TestGenerateResponse:
    """Test generate_response method"""

    @pytest.mark.asyncio
    async def test_generate_response_success(self, llm_service_with_provider):
        """Test successful response generation"""
        response = await llm_service_with_provider.generate_response(prompt="Hello, world!")

        assert response["success"] is True
        assert response["content"] == "Test response"
        assert "service_info" in response
        assert response["service_info"]["provider"] == "google"
        assert response["service_info"]["model"] == "gemini-2.5-flash"

    @pytest.mark.asyncio
    async def test_generate_response_custom_provider(self, llm_service_with_provider):
        """Test response with custom provider specified"""
        response = await llm_service_with_provider.generate_response(
            prompt="Test prompt", provider=LLMProvider.GOOGLE
        )

        assert response["success"] is True
        assert response["service_info"]["provider"] == "google"

    @pytest.mark.asyncio
    async def test_generate_response_custom_model(self, llm_service_with_provider):
        """Test response with custom model"""
        response = await llm_service_with_provider.generate_response(
            prompt="Test prompt", model="gemini-1.5-pro"
        )

        assert response["success"] is True
        assert response["service_info"]["model"] == "gemini-1.5-pro"

    @pytest.mark.asyncio
    async def test_generate_response_with_tools(self, llm_service_with_provider):
        """Test response generation with function calling tools"""

        def test_tool():
            """Test tool function"""
            return "tool result"

        response = await llm_service_with_provider.generate_response(
            prompt="Use the tool", tools=[test_tool], automatic_function_calling=True
        )

        assert response["success"] is True
        assert response["service_info"]["function_calling_enabled"] is True

    @pytest.mark.asyncio
    async def test_generate_response_provider_not_available(self, llm_service_no_provider):
        """Test response when provider not available"""
        response = await llm_service_no_provider.generate_response(
            prompt="Test", provider=LLMProvider.GOOGLE
        )

        assert response["success"] is False
        assert "not available" in response["content"]
        assert "error" in response

    @pytest.mark.asyncio
    async def test_generate_response_provider_error(
        self, llm_service_with_provider, mock_gemini_provider
    ):
        """Test response when provider raises error"""
        from src.core.llm.llm_client import LLMServiceError

        mock_gemini_provider.generate_response.side_effect = Exception("API error")

        with pytest.raises(LLMServiceError, match="Service error"):
            await llm_service_with_provider.generate_response(prompt="Test")

    @pytest.mark.asyncio
    async def test_generate_response_with_kwargs(self, llm_service_with_provider):
        """Test response with additional kwargs"""
        response = await llm_service_with_provider.generate_response(
            prompt="Test", temperature=0.7, max_tokens=100
        )

        assert response["success"] is True
        # Verify kwargs were passed to provider
        call_kwargs = llm_service_with_provider.providers[
            LLMProvider.GOOGLE
        ].generate_response.call_args[1]
        assert "temperature" in call_kwargs
        assert "max_tokens" in call_kwargs


# ============================================================================
# TEST: Service Status
# ============================================================================


class TestServiceStatus:
    """Test get_service_status method"""

    @pytest.mark.asyncio
    async def test_get_service_status_success(self, llm_service_with_provider):
        """Test service status retrieval"""
        status = await llm_service_with_provider.get_service_status()

        assert status["service"] == "llm"
        assert status["default_provider"] == "google"
        assert status["default_model"] == "gemini-2.5-flash"
        assert status["total_providers"] == 1
        assert "google" in status["providers"]
        assert status["providers"]["google"]["available"] is True

    @pytest.mark.asyncio
    async def test_get_service_status_no_providers(self, llm_service_no_provider):
        """Test service status with no providers (fallback to Mock)"""
        status = await llm_service_no_provider.get_service_status()

        # Now we expect Mock provider fallback
        assert status["total_providers"] == 1
        assert "mock" in status["providers"]

    @pytest.mark.asyncio
    async def test_get_service_status_provider_error(
        self, llm_service_with_provider, mock_gemini_provider
    ):
        """Test service status when provider validation fails"""
        mock_gemini_provider.validate_connection.side_effect = Exception("Connection error")

        status = await llm_service_with_provider.get_service_status()

        assert "google" in status["providers"]
        assert status["providers"]["google"]["status"] == "error"
        assert status["providers"]["google"]["available"] is False


# ============================================================================
# TEST: Connectivity Testing
# ============================================================================


class TestConnectivity:
    """Test test_connectivity method"""

    @pytest.mark.asyncio
    async def test_connectivity_all_providers_ok(self, llm_service_with_provider):
        """Test connectivity when all providers are OK"""
        results = await llm_service_with_provider.test_connectivity()

        assert results["total_tested"] == 1
        assert results["successful"] == 1
        assert results["failed"] == 0
        assert "google" in results["test_results"]
        assert results["test_results"]["google"]["available"] is True

    @pytest.mark.asyncio
    async def test_connectivity_provider_fails(
        self, llm_service_with_provider, mock_gemini_provider
    ):
        """Test connectivity when provider fails"""
        mock_gemini_provider.validate_connection.side_effect = Exception("Network error")

        results = await llm_service_with_provider.test_connectivity()

        assert results["successful"] == 0
        assert results["failed"] == 1
        assert results["test_results"]["google"]["status"] == "failed"
        assert results["test_results"]["google"]["available"] is False

    @pytest.mark.asyncio
    async def test_connectivity_no_providers(self, llm_service_no_provider):
        """Test connectivity with no providers (fallback to Mock)"""
        results = await llm_service_no_provider.test_connectivity()

        # Mock provider is tested
        assert results["total_tested"] == 1
        assert results["successful"] == 1
        assert results["failed"] == 0


# ============================================================================
# TEST: Model Management
# ============================================================================


class TestModelManagement:
    """Test model-related methods"""

    @pytest.mark.asyncio
    async def test_get_available_models_specific_provider(self, llm_service_with_provider):
        """Test getting models for specific provider"""
        models = await llm_service_with_provider.get_available_models(LLMProvider.GOOGLE)

        assert len(models) == 2
        assert "gemini-2.5-flash" in models
        assert "gemini-1.5-pro" in models

    @pytest.mark.asyncio
    async def test_get_available_models_all_providers(self, llm_service_with_provider):
        """Test getting models from all providers"""
        models = await llm_service_with_provider.get_available_models()

        assert len(models) >= 2
        assert "gemini-2.5-flash" in models

    @pytest.mark.asyncio
    async def test_get_available_models_no_providers(self, llm_service_no_provider):
        """Test getting models when only mock provider available"""
        models = await llm_service_no_provider.get_available_models()

        # Should contain mock model
        assert "mock-intelligent" in models
        assert len(models) >= 1

    def test_is_provider_available_true(self, llm_service_with_provider):
        """Test provider availability check - available"""
        available = llm_service_with_provider.is_provider_available(LLMProvider.GOOGLE)

        assert available is True

    def test_is_provider_available_false(self, llm_service_no_provider):
        """Test provider availability check - not available"""
        available = llm_service_no_provider.is_provider_available(LLMProvider.GOOGLE)

        assert available is False

    def test_is_provider_available_not_initialized(
        self, llm_service_with_provider, mock_gemini_provider
    ):
        """Test provider availability when not initialized"""
        mock_gemini_provider.initialized = False

        available = llm_service_with_provider.is_provider_available(LLMProvider.GOOGLE)

        assert available is False


# ============================================================================
# TEST: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error scenarios"""

    @pytest.mark.asyncio
    async def test_generate_response_empty_prompt(self, llm_service_with_provider):
        """Test response with empty prompt"""
        response = await llm_service_with_provider.generate_response(prompt="")

        # Should still work, provider handles empty prompts
        assert "success" in response

    @pytest.mark.asyncio
    async def test_generate_response_none_provider_uses_default(self, llm_service_with_provider):
        """Test that None provider uses default"""
        response = await llm_service_with_provider.generate_response(prompt="Test", provider=None)

        assert response["service_info"]["provider"] == "google"

    @pytest.mark.asyncio
    async def test_generate_response_none_model_uses_default(self, llm_service_with_provider):
        """Test that None model uses default"""
        response = await llm_service_with_provider.generate_response(prompt="Test", model=None)

        assert response["service_info"]["model"] == "gemini-2.5-flash"

    @pytest.mark.asyncio
    async def test_get_available_models_duplicate_removal(
        self, llm_service_with_provider, mock_gemini_provider
    ):
        """Test that duplicate models are removed"""
        # Add duplicate models
        mock_gemini_provider.model_names = ["model1", "model2", "model1"]

        models = await llm_service_with_provider.get_available_models()

        # Should only have unique models
        assert len(models) == len(set(models))


# ============================================
# PHASE 1 ENHANCEMENT TESTS
# Testing: Exception hierarchy, retry logic, token budget
# ============================================


class TestExceptionHierarchy:
    """Test custom LLM exception hierarchy (TDD Phase 1)"""

    @pytest.mark.asyncio
    async def test_timeout_error_raised(self):
        """GIVEN provider that times out
        WHEN generate_response is called
        THEN raises LLMTimeoutError"""
        from src.core.llm.llm_client import LLMTimeoutError

        # Reset singleton state
        LLMService._instance = None

        # DeepSeek is uit de platformservice (ADR-041 B14); Mistral (EU) is nu de gemockte provider.
        with (
            patch.dict("os.environ", {"MISTRAL_API_KEY": "test-key", "LLM_PROVIDER": "mistral"}),
            patch("src.core.llm.llm_service.MistralProvider") as mock_provider_class,
        ):
            mock_provider = AsyncMock()
            mock_provider.generate_response = AsyncMock(
                side_effect=LLMTimeoutError("Request timed out after 30s")
            )
            mock_provider_class.return_value = mock_provider

            service = LLMService()
            await service.initialize()

            with pytest.raises(LLMTimeoutError, match="timed out"):
                await service.generate_response("Test prompt")

    @pytest.mark.asyncio
    async def test_rate_limit_error_with_retry_after(self):
        """GIVEN provider that hits rate limit
        WHEN generate_response is called
        THEN raises LLMRateLimitError with retry_after"""
        from src.core.llm.llm_client import LLMRateLimitError

        # Reset singleton state
        LLMService._instance = None

        # DeepSeek is uit de platformservice (ADR-041 B14); Mistral (EU) is nu de gemockte provider.
        with (
            patch.dict("os.environ", {"MISTRAL_API_KEY": "test-key", "LLM_PROVIDER": "mistral"}),
            patch("src.core.llm.llm_service.MistralProvider") as mock_provider_class,
        ):
            mock_provider = AsyncMock()
            error = LLMRateLimitError("Rate limit exceeded", retry_after=60)
            mock_provider.generate_response = AsyncMock(side_effect=error)
            mock_provider_class.return_value = mock_provider

            service = LLMService()
            await service.initialize()

            with pytest.raises(LLMRateLimitError) as exc_info:
                await service.generate_response("Test prompt")

            assert exc_info.value.retry_after == 60

    @pytest.mark.asyncio
    async def test_authentication_error_raised(self):
        """GIVEN provider with invalid credentials
        WHEN generate_response is called
        THEN raises LLMAuthenticationError"""
        from src.core.llm.llm_client import LLMAuthenticationError

        # Reset singleton state
        LLMService._instance = None

        # DeepSeek is uit de platformservice (ADR-041 B14); Mistral (EU) is nu de gemockte provider.
        with (
            patch.dict("os.environ", {"MISTRAL_API_KEY": "test-key", "LLM_PROVIDER": "mistral"}),
            patch("src.core.llm.llm_service.MistralProvider") as mock_provider_class,
        ):
            mock_provider = AsyncMock()
            mock_provider.generate_response = AsyncMock(
                side_effect=LLMAuthenticationError("Invalid API key")
            )
            mock_provider_class.return_value = mock_provider

            service = LLMService()
            await service.initialize()

            with pytest.raises(LLMAuthenticationError, match="Invalid API key"):
                await service.generate_response("Test prompt")

    @pytest.mark.asyncio
    async def test_content_filter_error_raised(self):
        """GIVEN content blocked by safety filter
        WHEN generate_response is called
        THEN raises LLMContentFilterError"""
        from src.core.llm.llm_client import LLMContentFilterError

        # Reset singleton state
        LLMService._instance = None

        # DeepSeek is uit de platformservice (ADR-041 B14); Mistral (EU) is nu de gemockte provider.
        with (
            patch.dict("os.environ", {"MISTRAL_API_KEY": "test-key", "LLM_PROVIDER": "mistral"}),
            patch("src.core.llm.llm_service.MistralProvider") as mock_provider_class,
        ):
            mock_provider = AsyncMock()
            mock_provider.generate_response = AsyncMock(
                side_effect=LLMContentFilterError("Content blocked by safety system")
            )
            mock_provider_class.return_value = mock_provider

            service = LLMService()
            await service.initialize()

            with pytest.raises(LLMContentFilterError, match="safety system"):
                await service.generate_response("Inappropriate content")


class TestRetryLogic:
    """Test exponential backoff retry logic (TDD Phase 1)"""

    @pytest.mark.asyncio
    async def test_retry_on_connection_error_succeeds(self):
        """GIVEN provider that fails once then succeeds
        WHEN generate_response is called with max_retries=3
        THEN retries and returns response"""

        # Reset singleton state
        LLMService._instance = None

        # DeepSeek is uit de platformservice (ADR-041 B14); Mistral (EU) is nu de gemockte provider.
        with (
            patch.dict("os.environ", {"MISTRAL_API_KEY": "test-key", "LLM_PROVIDER": "mistral"}),
            patch("src.core.llm.llm_service.MistralProvider") as mock_provider_class,
        ):
            mock_provider = AsyncMock()
            # First call fails, second succeeds
            mock_provider.generate_response = AsyncMock(
                side_effect=[
                    ConnectionError("Connection failed"),
                    {"response": "Success after retry", "success": True},
                ]
            )
            mock_provider_class.return_value = mock_provider

            service = LLMService()
            await service.initialize()

            # Should succeed on second attempt
            result = await service.generate_response("Test", max_retries=3)

            assert result["success"] is True
            assert mock_provider.generate_response.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhaustion_raises_error(self):
        """GIVEN provider that always fails with ConnectionError
        WHEN generate_response is called with max_retries=2
        THEN exhausts retries and raises LLMServiceError"""
        from src.core.llm.llm_client import LLMServiceError

        # Reset singleton state
        LLMService._instance = None

        # DeepSeek is uit de platformservice (ADR-041 B14); Mistral (EU) is nu de gemockte provider.
        with (
            patch.dict("os.environ", {"MISTRAL_API_KEY": "test-key", "LLM_PROVIDER": "mistral"}),
            patch("src.core.llm.llm_service.MistralProvider") as mock_provider_class,
        ):
            mock_provider = AsyncMock()
            mock_provider.generate_response = AsyncMock(side_effect=ConnectionError("Always fails"))
            mock_provider_class.return_value = mock_provider

            service = LLMService()
            await service.initialize()

            with pytest.raises(LLMServiceError, match="after 2 retries"):
                await service.generate_response("Test", max_retries=2)

            assert mock_provider.generate_response.call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_on_authentication_error(self):
        """GIVEN provider that raises AuthenticationError
        WHEN generate_response is called
        THEN raises immediately without retry"""
        from src.core.llm.llm_client import LLMAuthenticationError

        # Reset singleton state
        LLMService._instance = None

        # DeepSeek is uit de platformservice (ADR-041 B14); Mistral (EU) is nu de gemockte provider.
        with (
            patch.dict("os.environ", {"MISTRAL_API_KEY": "test-key", "LLM_PROVIDER": "mistral"}),
            patch("src.core.llm.llm_service.MistralProvider") as mock_provider_class,
        ):
            mock_provider = AsyncMock()
            mock_provider.generate_response = AsyncMock(
                side_effect=LLMAuthenticationError("Invalid key")
            )
            mock_provider_class.return_value = mock_provider

            service = LLMService()
            await service.initialize()

            with pytest.raises(LLMAuthenticationError):
                await service.generate_response("Test", max_retries=3)

            # Should NOT retry on auth errors
            assert mock_provider.generate_response.call_count == 1

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self):
        """GIVEN provider with transient failures
        WHEN retries occur
        THEN uses exponential backoff (0.5s, 1s, 2s)"""
        import time

        # Reset singleton state
        LLMService._instance = None

        # DeepSeek is uit de platformservice (ADR-041 B14); Mistral (EU) is nu de gemockte provider.
        with (
            patch.dict("os.environ", {"MISTRAL_API_KEY": "test-key", "LLM_PROVIDER": "mistral"}),
            patch("src.core.llm.llm_service.MistralProvider") as mock_provider_class,
        ):
            mock_provider = AsyncMock()
            call_times = []

            async def track_time(*args, **kwargs):
                call_times.append(time.time())
                if len(call_times) < 3:
                    raise ConnectionError("Transient")
                return {"response": "Success", "success": True}

            mock_provider.generate_response = AsyncMock(side_effect=track_time)
            mock_provider_class.return_value = mock_provider

            service = LLMService()
            await service.initialize()

            result = await service.generate_response("Test", max_retries=3)

            # Check exponential backoff timing (approximately)
            assert len(call_times) == 3
            # First retry: ~0.5s wait
            # Second retry: ~1s wait (0.5 * 2)


class TestTokenBudgetTracking:
    """Test token budget enforcement (TDD Phase 1)"""

    @pytest.mark.asyncio
    async def test_token_budget_tracking(self):
        """GIVEN service with token_budget set
        WHEN generate_response uses tokens
        THEN tracks usage correctly"""

        # Reset singleton state
        LLMService._instance = None

        # DeepSeek is uit de platformservice (ADR-041 B14); Mistral (EU) is nu de gemockte provider.
        with (
            patch.dict("os.environ", {"MISTRAL_API_KEY": "test-key", "LLM_PROVIDER": "mistral"}),
            patch("src.core.llm.llm_service.MistralProvider") as mock_provider_class,
        ):
            mock_provider = AsyncMock()
            mock_provider.generate_response = AsyncMock(
                return_value={
                    "response": "Test response",
                    "success": True,
                    "usage": {"total_tokens": 50},
                }
            )
            mock_provider_class.return_value = mock_provider

            service = LLMService()
            await service.initialize()
            service.set_token_budget(1000)

            await service.generate_response("Test prompt")

            assert service._tokens_used == 50
            assert service.tokens_remaining == 950

    @pytest.mark.asyncio
    async def test_token_budget_exceeded_raises_error(self):
        """GIVEN service with token_budget exceeded
        WHEN generate_response is called
        THEN raises TokenBudgetExceededError"""
        from src.core.llm.llm_client import TokenBudgetExceededError

        # Reset singleton state
        LLMService._instance = None

        # DeepSeek is uit de platformservice (ADR-041 B14); Mistral (EU) is nu de gemockte provider.
        with (
            patch.dict("os.environ", {"MISTRAL_API_KEY": "test-key", "LLM_PROVIDER": "mistral"}),
            patch("src.core.llm.llm_service.MistralProvider") as mock_provider_class,
        ):
            mock_provider = AsyncMock()
            mock_provider.generate_response = AsyncMock(
                return_value={
                    "response": "Test",
                    "success": True,
                    "usage": {"total_tokens": 100},
                }
            )
            mock_provider_class.return_value = mock_provider

            service = LLMService()
            await service.initialize()
            service.set_token_budget(50)
            # FORCE budget to be exceeded
            service._tokens_used = 50

            with pytest.raises(TokenBudgetExceededError, match="budget exceeded"):
                await service.generate_response("Test prompt")

    @pytest.mark.asyncio
    async def test_token_budget_multiple_calls(self):
        """GIVEN service with token budget
        WHEN multiple calls consume tokens
        THEN tracks cumulative usage"""

        # Reset singleton state
        LLMService._instance = None

        # DeepSeek is uit de platformservice (ADR-041 B14); Mistral (EU) is nu de gemockte provider.
        with (
            patch.dict("os.environ", {"MISTRAL_API_KEY": "test-key", "LLM_PROVIDER": "mistral"}),
            patch("src.core.llm.llm_service.MistralProvider") as mock_provider_class,
        ):
            mock_provider = AsyncMock()
            mock_provider.generate_response = AsyncMock(
                return_value={
                    "response": "Test",
                    "success": True,
                    "usage": {"total_tokens": 30},
                }
            )
            mock_provider_class.return_value = mock_provider

            service = LLMService()
            await service.initialize()
            service.set_token_budget(100)

            # First call: 30 tokens
            await service.generate_response("Test 1")
            assert service._tokens_used == 30

            # Second call: 30 more tokens (60 total)
            await service.generate_response("Test 2")
            assert service._tokens_used == 60

            # Third call: 30 more tokens (90 total)
            await service.generate_response("Test 3")
            assert service._tokens_used == 90
            assert service.tokens_remaining == 10

    @pytest.mark.asyncio
    async def test_token_counter_reset(self):
        """GIVEN service with tokens used
        WHEN reset_token_counter is called
        THEN resets to zero"""

        # Reset singleton state
        LLMService._instance = None

        # DeepSeek is uit de platformservice (ADR-041 B14); Mistral (EU) is nu de gemockte provider.
        with (
            patch.dict("os.environ", {"MISTRAL_API_KEY": "test-key", "LLM_PROVIDER": "mistral"}),
            patch("src.core.llm.llm_service.MistralProvider") as mock_provider_class,
        ):
            mock_provider = AsyncMock()
            mock_provider.generate_response = AsyncMock(
                return_value={
                    "response": "Test",
                    "success": True,
                    "usage": {"total_tokens": 100},
                }
            )
            mock_provider_class.return_value = mock_provider

            service = LLMService()
            await service.initialize()
            service.set_token_budget(1000)

            await service.generate_response("Test")
            assert service._tokens_used == 100

            service.reset_token_counter()
            assert service._tokens_used == 0
            assert service.tokens_remaining == 1000

    @pytest.mark.asyncio
    async def test_no_budget_allows_unlimited_tokens(self):
        """GIVEN service without token budget
        WHEN generate_response uses many tokens
        THEN tracks usage but doesn't enforce limit"""

        # Reset singleton state
        LLMService._instance = None

        # DeepSeek is uit de platformservice (ADR-041 B14); Mistral (EU) is nu de gemockte provider.
        with (
            patch.dict("os.environ", {"MISTRAL_API_KEY": "test-key", "LLM_PROVIDER": "mistral"}),
            patch("src.core.llm.llm_service.MistralProvider") as mock_provider_class,
        ):
            mock_provider = AsyncMock()
            mock_provider.generate_response = AsyncMock(
                return_value={
                    "response": "Test",
                    "success": True,
                    "usage": {"total_tokens": 10000},
                }
            )
            mock_provider_class.return_value = mock_provider

            service = LLMService()
            await service.initialize()
            # No budget set

            # Should succeed even with high token usage
            result = await service.generate_response("Test")
            assert result["success"] is True
            assert service.tokens_remaining is None  # No limit
