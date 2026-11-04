"""
Unit tests for GDPR Enforcer - Slice 6

Tests data minimization and classification enforcement.
Sprint 4 - S4.6: GDPR compliance checks
"""

from unittest.mock import Mock

import pytest


class TestGDPREnforcer:
    """Test suite for GDPR data enforcement."""

    def test_data_minimization_success(self):
        """Payload with only required fields should pass."""
        from src.core.governance.gdpr_enforcer import GDPREnforcer

        enforcer = GDPREnforcer()

        # Mock schema requires only: email, name
        schema = {"required_fields": ["email", "name"], "optional_fields": ["phone"]}

        # Payload contains exactly required fields
        payload = {"email": "user@example.com", "name": "John Doe"}

        # Should succeed
        result = enforcer.enforce_minimization(payload, schema)

        assert result is True

    def test_data_minimization_with_optional_allowed(self):
        """Optional fields should be allowed."""
        from src.core.governance.gdpr_enforcer import GDPREnforcer

        enforcer = GDPREnforcer()

        # Mock schema
        schema = {"required_fields": ["email"], "optional_fields": ["name", "phone"]}

        # Payload with optional field
        payload = {"email": "user@example.com", "name": "John Doe"}

        result = enforcer.enforce_minimization(payload, schema)

        assert result is True

    def test_data_minimization_violation(self):
        """Payload with excessive data should raise MinimizationError."""
        from src.core.governance.gdpr_enforcer import GDPREnforcer, MinimizationError

        enforcer = GDPREnforcer()

        # Mock schema requires only email
        schema = {"required_fields": ["email"], "optional_fields": []}

        # Payload contains excessive fields
        payload = {
            "email": "user@example.com",
            "ssn": "123-45-6789",  # NOT in schema - violation!
            "credit_card": "1234-5678-9012-3456",
        }

        # Should raise MinimizationError
        with pytest.raises(MinimizationError) as exc_info:
            enforcer.enforce_minimization(payload, schema)

        assert "Unnecessary fields detected" in str(exc_info.value)
        assert "ssn" in str(exc_info.value)
        assert "credit_card" in str(exc_info.value)

    def test_classification_public_data_allowed(self):
        """Public data can be accessed by all tools."""
        from src.core.governance.gdpr_enforcer import GDPREnforcer

        enforcer = GDPREnforcer()

        # Mock data with public classification
        data_tags = {"classification": "public"}

        # Low trust tool (e.g., external API)
        tool_trust_level = "low"

        # Public data accessible to low trust
        result = enforcer.enforce_classification(data_tags, tool_trust_level)

        assert result is True

    def test_classification_pii_requires_high_trust(self):
        """PII data requires high trust tool."""
        from src.core.governance.gdpr_enforcer import ClassificationError, GDPREnforcer

        enforcer = GDPREnforcer()

        # Mock data with PII classification
        data_tags = {"classification": "pii"}

        # Low trust tool attempts access
        tool_trust_level = "low"

        # Should raise ClassificationError
        with pytest.raises(ClassificationError) as exc_info:
            enforcer.enforce_classification(data_tags, tool_trust_level)

        assert "Tool trust level 'low' insufficient for data classification 'pii'" in str(
            exc_info.value
        )

    def test_classification_confidential_requires_medium_or_high(self):
        """Confidential data requires at least medium trust."""
        from src.core.governance.gdpr_enforcer import ClassificationError, GDPREnforcer

        enforcer = GDPREnforcer()

        # Confidential data
        data_tags = {"classification": "confidential"}

        # Test low trust - should fail
        with pytest.raises(ClassificationError):
            enforcer.enforce_classification(data_tags, "low")

        # Test medium trust - should succeed
        result_medium = enforcer.enforce_classification(data_tags, "medium")
        assert result_medium is True

        # Test high trust - should succeed
        result_high = enforcer.enforce_classification(data_tags, "high")
        assert result_high is True

    def test_missing_required_fields_detected(self):
        """Payload missing required fields should raise error."""
        from src.core.governance.gdpr_enforcer import GDPREnforcer, MinimizationError

        enforcer = GDPREnforcer()

        # Schema requires email AND name
        schema = {"required_fields": ["email", "name"], "optional_fields": []}

        # Payload missing 'name'
        payload = {"email": "user@example.com"}

        # Should raise error
        with pytest.raises(MinimizationError) as exc_info:
            enforcer.enforce_minimization(payload, schema)

        assert "Missing required fields" in str(exc_info.value)
        assert "name" in str(exc_info.value)

    def test_audit_log_gdpr_violations(self):
        """GDPR violations should be logged for audit."""
        from src.core.governance.gdpr_enforcer import GDPREnforcer, MinimizationError

        enforcer = GDPREnforcer()

        schema = {"required_fields": ["email"], "optional_fields": []}

        payload = {"email": "user@example.com", "ssn": "123-45-6789"}

        # Capture violation
        with pytest.raises(MinimizationError):
            enforcer.enforce_minimization(payload, schema)

        # Verify violation was logged
        assert len(enforcer.violation_log) > 0
        last_violation = enforcer.violation_log[-1]
        assert last_violation["type"] == "minimization"
        assert "ssn" in last_violation["excessive_fields"]


class TestDetectPii:
    """Test suite for GDPR PII detection heuristics."""

    @pytest.fixture
    def enforcer(self):
        from src.core.governance.gdpr_enforcer import GDPREnforcer

        return GDPREnforcer()

    def test_empty_payload_returns_empty(self, enforcer):
        assert enforcer.detect_pii({}) == []

    def test_no_pii_in_simple_strings(self, enforcer):
        payload = {"name": "John", "city": "Amsterdam", "status": "active"}
        assert enforcer.detect_pii(payload) == []

    def test_detects_email(self, enforcer):
        payload = {"contact": "john.doe@example.com"}
        assert "email" in enforcer.detect_pii(payload)

    def test_detects_phone_us_format(self, enforcer):
        payload = {"phone": "555-123-4567"}
        assert "phone" in enforcer.detect_pii(payload)

    def test_detects_phone_with_country_code(self, enforcer):
        payload = {"mobile": "+1-555-123-4567"}
        assert "phone" in enforcer.detect_pii(payload)

    def test_detects_ssn(self, enforcer):
        payload = {"ssn": "123-45-6789"}
        assert "ssn" in enforcer.detect_pii(payload)

    def test_detects_credit_card(self, enforcer):
        """Een ECHT kaartnummer (Luhn-geldig). 4111... is het standaard testnummer.

        Hier stond `1234-5678-9012-3456`, en die legde het defect vast in plaats van het
        gedrag: dat nummer heeft geen geldige Luhn en is dus geen kaartnummer. Zolang niemand
        op de uitkomst HANDELDE viel dat niet op; toen de InputGuard erop ging blokkeren werd
        elke getallenreeks van 13-20 cijfers een geweigerd chatbericht (Gate 2, 2026-09-22).
        """
        payload = {"cc": "4111-1111-1111-1111"}
        assert "credit_card" in enforcer.detect_pii(payload)

    @pytest.mark.parametrize(
        "waarde,wat",
        [
            ("1234-5678-9012-3456", "verzonnen nummer, geen geldige Luhn"),
            ("20260922145501", "een buildnummer"),
            ("1726937461123", "een tijdstempel in milliseconden"),
            ("9780306406157", "een ISBN"),
        ],
    )
    def test_een_getallenreeks_zonder_geldige_luhn_is_geen_kaartnummer(
        self, enforcer, waarde, wat
    ):
        """De vier gevallen die in Gate 2 zijn gemeten, elk als eigen regel.

        Het patroon voor `credit_card` is elke reeks van 13-20 cijfers. Zonder
        controlegetal is dat geen detectie maar een gok, en de module schrijft zelf voor dat
        een kale patroontreffer voor dit soort types nooit volstaat.
        """
        assert "credit_card" not in enforcer.detect_pii({"x": waarde}), wat

    def test_detects_multiple_pii_types(self, enforcer):
        payload = {
            "email": "test@example.com",
            "phone": "555-123-4567",
            "name": "Alice",
        }
        detected = enforcer.detect_pii(payload)
        assert "email" in detected
        assert "phone" in detected
        assert len(detected) == 2

    def test_nested_dict_traversal(self, enforcer):
        payload = {"user": {"email": "nested@example.com"}, "meta": {"id": 42}}
        assert "email" in enforcer.detect_pii(payload)

    def test_list_traversal(self, enforcer):
        payload = {"contacts": ["555-123-4567", "no-pii-here"]}
        assert "phone" in enforcer.detect_pii(payload)

    def test_deeply_nested_structure(self, enforcer):
        payload = {
            "level1": {
                "level2": [
                    {"level3": {"email": "deep@example.com"}},
                ]
            }
        }
        assert "email" in enforcer.detect_pii(payload)

    def test_deduplicates_pii_types(self, enforcer):
        payload = {
            "email1": "a@example.com",
            "email2": "b@example.com",
        }
        detected = enforcer.detect_pii(payload)
        assert detected == ["email"]

    def test_mixed_payload_with_some_pii(self, enforcer):
        payload = {
            "title": "Project Update",
            "owner": "Alice",
            "owner_email": "alice@corp.com",
            "tags": ["urgent", "internal"],
        }
        detected = enforcer.detect_pii(payload)
        assert detected == ["email"]

    def test_detects_bsn(self, enforcer):
        """AUDIT-002: a real, elfproef-valid BSN must be detected."""
        payload = {"employee_id": "111222333"}
        assert "bsn" in enforcer.detect_pii(payload)

    def test_does_not_detect_invalid_bsn_checksum(self, enforcer):
        """AUDIT-002: a 9-digit number that fails the elfproef is not a BSN --
        the checksum, not just the digit count, must gate detection."""
        payload = {"order_id": "123456789"}
        assert "bsn" not in enforcer.detect_pii(payload)

    def test_detects_iban(self, enforcer):
        """AUDIT-002: a real, mod-97-valid IBAN must be detected."""
        payload = {"bank_account": "NL91ABNA0417164300"}
        assert "iban" in enforcer.detect_pii(payload)

    def test_does_not_detect_invalid_iban_checksum(self, enforcer):
        """AUDIT-002: an IBAN-shaped string with a failing checksum is not PII."""
        payload = {"reference": "NL00ABNA0417164300"}
        assert "iban" not in enforcer.detect_pii(payload)

    def test_redact_pii_only_masks_checksum_valid_bsn(self, enforcer):
        """redact_pii must not blindly mask every 9-digit number as a BSN."""
        text = "Valid BSN 111222333 but order 123456789 is not PII."
        masked, token_map = enforcer.redact_pii(text)
        assert "111222333" not in masked
        assert "123456789" in masked
        assert len(token_map) == 1
