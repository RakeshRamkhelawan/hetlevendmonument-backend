import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.llm.provider_factory import LLMProviderProtocol
from src.core.sandbox.doctor_agent import DOCTOR_SYSTEM_PROMPT, DoctorAgent
from src.core.sandbox.resilient_executor import HealingPolicy


@pytest.fixture
def mock_llm_provider():
    provider = MagicMock(spec=LLMProviderProtocol)
    provider.generate_text = AsyncMock()
    return provider


@pytest.fixture
def doctor_agent(mock_llm_provider):
    return DoctorAgent(llm_provider=mock_llm_provider)


@pytest.mark.asyncio
async def test_diagnose_and_fix_valid_json(doctor_agent, mock_llm_provider):
    """Test clear path with valid JSON response"""

    # Mock LLM response
    fixed_code = "print('Hello World')"
    mock_response = json.dumps(
        {
            "analysis": "Missing quote",
            "error_type": "SYNTAX",
            "fix_description": "Added quote",
            "patched_code": fixed_code,
        }
    )
    mock_llm_provider.generate_text.return_value = mock_response

    result = await doctor_agent.diagnose_and_fix(
        code="print('Hello",
        error_output="SyntaxError: EOL",
        policy=HealingPolicy(model_name="test-model"),
    )

    assert result["patched_code"] == fixed_code
    assert result["error_type"] == "SYNTAX"

    # Verify prompt was called correctly
    mock_llm_provider.generate_text.assert_called_once()
    kwargs = mock_llm_provider.generate_text.call_args.kwargs
    assert kwargs["system_instruction"] == DOCTOR_SYSTEM_PROMPT
    assert "SyntaxError: EOL" in kwargs["prompt"]


@pytest.mark.asyncio
async def test_diagnose_logic_error_assertion(doctor_agent, mock_llm_provider):
    """Test handling of logical errors (Test-Driven Healing)"""

    code = "def add(a, b): return a - b"  # Buggy code
    error = "AssertionError: assert add(2, 3) == 5"

    mock_response = json.dumps(
        {
            "analysis": "Function subtracts instead of adds",
            "error_type": "LOGIC",
            "fix_description": "Changed operator",
            "patched_code": "def add(a, b): return a + b",
        }
    )
    mock_llm_provider.generate_text.return_value = mock_response

    result = await doctor_agent.diagnose_and_fix(code, error, HealingPolicy())

    assert result["patched_code"] == "def add(a, b): return a + b"
    assert "AssertionError" in mock_llm_provider.generate_text.call_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_diagnose_with_history(doctor_agent, mock_llm_provider):
    """Test that history is included in the prompt"""
    history = [{"code": "print('fail')", "error": "NameError", "output": ""}]

    mock_llm_provider.generate_text.return_value = json.dumps(
        {
            "patched_code": "print('success')",
            "analysis": "fixed name",
            "error_type": "LOGIC",
            "fix_description": "fix",
        }
    )

    await doctor_agent.diagnose_and_fix("code", "error", HealingPolicy(), history=history)

    prompt = mock_llm_provider.generate_text.call_args.kwargs["prompt"]
    assert "PREVIOUS ATTEMPTS" in prompt
    assert "NameError" in prompt


@pytest.mark.asyncio
async def test_diagnose_handles_markdown_json(doctor_agent, mock_llm_provider):
    """Test parsing when LLM wraps JSON in markdown code blocks"""

    mock_response = """
    Here is the fix:
    ```json
    {
        "patched_code": "fixed"
    }
    ```
    """
    mock_llm_provider.generate_text.return_value = mock_response

    result = await doctor_agent.diagnose_and_fix("code", "err", HealingPolicy())
    assert result["patched_code"] == "fixed"


@pytest.mark.asyncio
async def test_diagnose_handles_invalid_json(doctor_agent, mock_llm_provider):
    """Test fallback when LLM returns garbage"""

    mock_llm_provider.generate_text.return_value = "I cannot fix this."

    result = await doctor_agent.diagnose_and_fix("original", "err", HealingPolicy())

    # Should return original code structure with error
    assert result["patched_code"] == "original"
    assert result["error"] == "Invalid LLM format"


@pytest.mark.asyncio
async def test_diagnose_provider_failure(doctor_agent, mock_llm_provider):
    """Test exception handling"""

    mock_llm_provider.generate_text.side_effect = Exception("API Down")

    result = await doctor_agent.diagnose_and_fix("original", "err", HealingPolicy())

    assert result["patched_code"] == "original"
    assert "API Down" in result["error"]


@pytest.mark.asyncio
async def test_lazy_loading_integration():
    """Test that get_llm_provider is called if no provider injected"""
    with patch(
        "src.core.sandbox.doctor_agent.get_llm_provider"
    ) as mock_get_prov:
        mock_provider = MagicMock(spec=LLMProviderProtocol)
        mock_provider.generate_text = AsyncMock(return_value='{"patched_code": "k"}')
        mock_get_prov.return_value = mock_provider

        agent = DoctorAgent()  # No provider injected
        await agent.diagnose_and_fix("c", "e", HealingPolicy())

        mock_get_prov.assert_called_once()
        mock_provider.generate_text.assert_called_once()
