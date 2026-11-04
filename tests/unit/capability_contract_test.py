"""
TDD Tests for TKT-F0-01: Capability Contract Core
Phase 0 - Contract Foundation

Tests: Happy + 2 Unhappy paths per requirement
"""

from datetime import datetime
from typing import Any, Dict, Optional

import pytest
from pydantic import ValidationError

# These imports will fail initially (RED phase)
# We'll create them to make tests pass (GREEN phase)
from src.core.contracts.capability import (
    AuditPolicy,
    CapabilityContract,
    CapabilityKey,
    FallbackPolicy,
    InputSchema,
    OutputSchema,
    RetryPolicy,
)
from src.core.contracts.resolver import CapabilityResolver


class TestCapabilityContractModel:
    """Happy and unhappy tests for Capability Contract data model"""

    def test_happy_valid_contract_creation(self):
        """Happy: Valid contract with all required fields -> success"""
        # Arrange
        contract_data = {
            "capability_key": "email.send",
            "input_schema": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "format": "email"},
                    "subject": {"type": "string", "maxLength": 200},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject"],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                    "status": {"type": "string", "enum": ["sent", "queued"]},
                },
            },
            "retry_policy": {
                "max_attempts": 3,
                "backoff_strategy": "exponential",
                "initial_delay_ms": 1000,
            },
            "fallback_policy": {
                "enabled": True,
                "fallback_capability": "email.send_backup",
                "timeout_ms": 30000,
            },
            "idempotency_key": {
                "enabled": True,
                "key_format": "{tenant_id}:{workflow_id}:{node_id}",
            },
            "audit_policy": {"log_level": "info", "include_payload": True, "retention_days": 90},
        }

        # Act
        contract = CapabilityContract(**contract_data)

        # Assert
        assert contract.capability_key == "email.send"
        assert contract.input_schema["type"] == "object"
        assert contract.retry_policy.max_attempts == 3
        assert contract.fallback_policy.enabled is True
        assert contract.idempotency_key.enabled is True
        assert contract.audit_policy.retention_days == 90

    def test_unhappy_unknown_capability_key_rejected(self):
        """Unhappy A: unknown capability_key -> validation error"""
        # Arrange
        invalid_data = {
            "capability_key": "",  # Empty key should fail
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        }

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            CapabilityContract(**invalid_data)

        assert "capability_key" in str(exc_info.value)

    def test_unhappy_schema_mismatch_rejected(self):
        """Unhappy B: input schema mismatch -> reject before side effects"""
        # Arrange
        contract = CapabilityContract(
            capability_key="test.action",
            input_schema={
                "type": "object",
                "properties": {"required_field": {"type": "string"}},
                "required": ["required_field"],
            },
            output_schema={"type": "object"},
        )

        invalid_input = {"missing_required_field": "value"}  # Missing 'required_field'

        # Act
        is_valid, errors = contract.validate_input(invalid_input)

        # Assert
        assert is_valid is False
        assert len(errors) > 0
        assert "required_field" in str(errors)


class TestCapabilityResolver:
    """Tests for capability resolution in workflow execution path"""

    @pytest.fixture
    def resolver(self):
        """Create resolver with test capabilities"""
        registry = {
            "email.send": CapabilityContract(
                capability_key="email.send",
                input_schema={
                    "type": "object",
                    "properties": {"to": {"type": "string"}},
                    "required": ["to"],  # Make 'to' required for validation
                },
                output_schema={"type": "object"},
            ),
            "sms.send": CapabilityContract(
                capability_key="sms.send",
                input_schema={
                    "type": "object",
                    "properties": {"phone": {"type": "string"}},
                    "required": ["phone"],
                },
                output_schema={"type": "object"},
            ),
        }
        return CapabilityResolver(registry)

    def test_happy_valid_capability_resolution(self, resolver):
        """Happy: valid node -> capability resolution succeeds"""
        # Arrange
        node_config = {"capability_key": "email.send", "inputs": {"to": "test@example.com"}}

        # Act
        result = resolver.resolve(node_config)

        # Assert
        assert result.success is True
        assert result.contract.capability_key == "email.send"
        assert result.errors == []

    def test_unhappy_unknown_capability_key(self, resolver):
        """Unhappy A: unknown capability_key -> validation error"""
        # Arrange
        node_config = {"capability_key": "nonexistent.action", "inputs": {}}

        # Act
        result = resolver.resolve(node_config)

        # Assert
        assert result.success is False
        assert "nonexistent.action" in result.errors[0]
        assert result.contract is None

    def test_unhappy_input_schema_mismatch(self, resolver):
        """Unhappy B: input schema mismatch -> execute blocked with error detail"""
        # Arrange
        node_config = {
            "capability_key": "email.send",
            "inputs": {"invalid_field": "value"},  # Missing 'to' field
        }

        # Act
        result = resolver.resolve(node_config)

        # Assert
        assert result.success is False
        assert len(result.errors) > 0
        assert "to" in str(result.errors) or "schema" in str(result.errors).lower()


class TestCapabilityContractIntegration:
    """Integration-level tests for contract enforcement"""

    def test_contract_enforced_before_execution(self):
        """
        Integration test: Contract must be resolved before any side effects occur.
        This prevents partial executions with invalid data.
        """
        # Arrange
        contract = CapabilityContract(
            capability_key="payment.charge",
            input_schema={
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "minimum": 0.01},
                    "currency": {"type": "string", "enum": ["EUR", "USD"]},
                },
                "required": ["amount", "currency"],
            },
            output_schema={"type": "object"},
        )

        # Invalid input (negative amount)
        invalid_payment = {"amount": -10.00, "currency": "EUR"}

        # Act
        is_valid, errors = contract.validate_input(invalid_payment)

        # Assert - validation should fail BEFORE any execution
        assert is_valid is False
        assert "amount" in str(errors) or "minimum" in str(errors)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
