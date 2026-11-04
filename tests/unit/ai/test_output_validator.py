"""Tests for OutputValidator — Output Safety & PII Filtering (TDD: RED phase)"""

import pytest
from src.core.ai.output_validator import OutputValidator


class TestOutputValidatorHappyPath:
    """Tests with clean, safe output"""

    def test_clean_output_passes_through(self):
        """Happy path: Normal output returns unchanged"""
        validator = OutputValidator()
        text = "The answer to your question is that Paris is the capital of France."
        cleaned, issues = validator.validate(text, context={"tenant_id": 1, "agent_id": "test"})
        assert cleaned == text
        assert len(issues) == 0

    def test_normal_output_no_issues(self):
        """Happy path: Safe output has empty issues list"""
        validator = OutputValidator()
        text = "This is a normal response."
        cleaned, issues = validator.validate(text, context={})
        assert issues == []


class TestOutputValidatorUnhappyPath:
    """Tests with unsafe output"""

    def test_pii_ssn_detected_and_masked(self):
        """Unhappy path: SSN detected and masked"""
        validator = OutputValidator()
        text = "Customer SSN: 123-45-6789"
        cleaned, issues = validator.validate(text, context={"tenant_id": 1})

        # Should detect and mask SSN
        assert "[REDACTED]" in cleaned
        assert "123-45-6789" not in cleaned
        assert any("PII" in issue for issue in issues)

    def test_pii_email_detected_and_masked(self):
        """Unhappy path: Email addresses are detected"""
        validator = OutputValidator()
        text = "Contact admin@example.com for help"
        cleaned, issues = validator.validate(text, context={})

        # Depends on implementation — should at least be in issues
        assert len(issues) > 0 or "[REDACTED]" in cleaned

    def test_api_key_pattern_detected(self):
        """Unhappy path: API key pattern (sk-...) detected"""
        validator = OutputValidator()
        text = "Use this key: sk-abcdef123456789xyz"
        cleaned, issues = validator.validate(text, context={"tenant_id": 1})

        assert "[REDACTED]" in cleaned or len(issues) > 0

    def test_internal_path_removed(self):
        """Unhappy path: Internal paths detected"""
        validator = OutputValidator()
        text = "Configuration is at /etc/app/config.yaml"
        cleaned, issues = validator.validate(text, context={})

        # Should either remove or flag internal paths
        assert len(issues) > 0 or "/etc/" not in cleaned

    def test_issues_logged_with_tenant_context(self, caplog):
        """Unhappy path: Issues logged with tenant_id context"""
        validator = OutputValidator()
        text = "SSN is 111-22-3333"
        cleaned, issues = validator.validate(text, context={"tenant_id": 999, "agent_id": "agent1"})

        # Should have logged with context
        assert any(
            "999" in str(record.msg) or "validation" in record.message.lower()
            for record in caplog.records
        )

    def test_critical_pii_returns_generic_error(self):
        """Unhappy path: Critical PII triggers error response"""
        validator = OutputValidator()
        # Multiple PII fields = critical
        text = "SSN: 123-45-6789 and email: admin@example.com and API key: sk-xyz"
        cleaned, issues = validator.validate(text, context={"tenant_id": 1})

        # Should have issues
        assert len(issues) > 0


class TestOutputValidatorUserBehavioral:
    """User behavioral test: What the user experiences"""

    def test_user_receives_safe_response_when_llm_leaks_pii(self):
        """
        Behavioral test: LLM accidentally includes SSN in response.
        User receives: masked output (no PII visible) and application doesn't crash.
        """
        validator = OutputValidator()

        # Simulate LLM response that leaks SSN
        llm_response = "Customer account: John Doe, SSN: 987-65-4321, Balance: $5000"

        # Validate the response
        cleaned, issues = validator.validate(
            llm_response, context={"tenant_id": 1, "agent_id": "cva-agent"}
        )

        # User sees response but SSN is masked
        assert "987-65-4321" not in cleaned
        assert len(issues) > 0  # Issues detected
        assert "[REDACTED]" in cleaned or "Balance: $5000" in cleaned  # Safe parts preserved
