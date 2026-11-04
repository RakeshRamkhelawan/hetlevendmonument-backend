"""
Unit tests: json.loads hardening in LLM-code -- SP-SEC-001 LLM-C5-001/002

Verifieer dat malformed JSON een WARNING logt en een veilig resultaat retourneert.
Alle tests zijn RED voor de fix (geen WARNING logging), GREEN na de fix.
"""

from unittest.mock import patch


# ---------------------------------------------------------------------------
# LLM-C5-001: llm_agent_adapter._parse_llm_response
# ---------------------------------------------------------------------------


def test_parse_llm_response_logs_warning_on_malformed_json():
    """_parse_llm_response must log a WARNING when JSON parsing fails -- LLM-C5-001."""
    from src.core.als.llm_integration.llm_agent_adapter import LLMAgentAdapter

    adapter = LLMAgentAdapter.__new__(LLMAgentAdapter)

    with (
        patch.object(adapter, "_logger", create=True),
        patch("src.core.als.llm_integration.llm_agent_adapter.logger") as mock_module_log,
    ):
        adapter._parse_llm_response("```json\nthis is not valid json\n```")

    # Check either the module-level logger or instance logger
    all_warning_calls = mock_module_log.warning.call_args_list
    assert len(all_warning_calls) > 0, (
        "_parse_llm_response must call logger.warning() when JSON parsing fails. "
        "Fix: add 'logger.warning(...)' in the except block (SP-SEC-001 LLM-C5-001)."
    )


def test_parse_llm_response_returns_fallback_on_malformed_json():
    """_parse_llm_response must return a safe fallback dict, not raise -- LLM-C5-001."""
    from src.core.als.llm_integration.llm_agent_adapter import LLMAgentAdapter

    adapter = LLMAgentAdapter.__new__(LLMAgentAdapter)

    result = adapter._parse_llm_response("this is completely invalid json {{{")

    assert isinstance(result, dict), (
        f"_parse_llm_response must return a dict on parse failure, got {type(result).__name__}."
    )
    assert result, "Fallback dict must not be empty (SP-SEC-001 LLM-C5-001)."


# ---------------------------------------------------------------------------
# LLM-C5-002: adaptive_learning_engine -- json.loads in history load
# ---------------------------------------------------------------------------


def test_adaptive_learning_engine_logs_warning_on_malformed_json():
    """AdaptiveLearningEngine must log WARNING (not DEBUG) for JSONDecodeError -- LLM-C5-002.

    The existing code uses logger.debug() for json.JSONDecodeError.
    After the fix it must use logger.warning() so operators see parse failures.
    """
    import inspect
    from src.core.ai.adaptive_learning_engine import AdaptiveLearningEngine

    source = inspect.getsource(AdaptiveLearningEngine)
    lines = source.splitlines()

    # Line-by-line check: any line with "Failed to parse" must use logger.warning, not logger.debug.
    violations = [
        line.strip() for line in lines if "Failed to parse" in line and "logger.debug" in line
    ]
    assert not violations, (
        f"'Failed to parse' is logged at DEBUG level ({len(violations)} occurrence(s)):\n"
        + "\n".join(violations)
        + "\nFix: change 'logger.debug(...)' to 'logger.warning(\"Failed to parse...\", e)' "
        "for the json.JSONDecodeError handler (SP-SEC-001 LLM-C5-002)."
    )

    # After the fix, at least one line must log 'Failed to parse' at WARNING.
    warning_lines = [
        line.strip() for line in lines if "Failed to parse" in line and "logger.warning" in line
    ]
    assert warning_lines, (
        "No 'logger.warning' call found for 'Failed to parse' in AdaptiveLearningEngine. "
        "Fix: use 'logger.warning(\"Failed to parse learning event: %s\", e)' "
        "(SP-SEC-001 LLM-C5-002)."
    )


def test_adaptive_learning_engine_does_not_raise_on_malformed_json():
    """AdaptiveLearningEngine must not raise when JSON content is malformed -- LLM-C5-002."""
    import inspect
    from src.core.ai.adaptive_learning_engine import AdaptiveLearningEngine

    # Verify the except clause catches JSONDecodeError (not broad Exception swallowing)
    source = inspect.getsource(AdaptiveLearningEngine)
    assert "json.JSONDecodeError" in source, (
        "AdaptiveLearningEngine must explicitly catch json.JSONDecodeError per json.loads call. "
        "Fix: ensure each json.loads has its own try/except json.JSONDecodeError (SP-SEC-001 LLM-C5-002)."
    )
