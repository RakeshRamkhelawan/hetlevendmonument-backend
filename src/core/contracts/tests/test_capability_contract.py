"""
TDD Tests voor Capability Contract (Taak 0.1)

Happy + Unhappy paths voor capability contract validatie.
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.core.contracts.capability import (
    AuditPolicy,
    CapabilityContract,
    CapabilityRegistry,
    CapabilityResolver,
    CapabilityValidationError,
    FallbackPolicy,
    RetryPolicy,
    SchemaMismatchError,
    UnknownCapabilityError,
)


class TestCapabilityContract:
    """Test suite voor CapabilityContract model."""

    def test_happy_path_create_valid_contract(self):
        """Happy path: Geldige capability contract aanmaken."""
        contract = CapabilityContract(
            capability_key="send_email",
            input_schema={
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject"],
            },
            output_schema={
                "type": "object",
                "properties": {"message_id": {"type": "string"}, "status": {"type": "string"}},
            },
            retry_policy=RetryPolicy(
                max_retries=3, backoff_strategy="exponential", initial_delay_ms=1000
            ),
            fallback_policy=FallbackPolicy(
                fallback_capability="send_email_backup", on_failure_types=["timeout", "rate_limit"]
            ),
            idempotency_key_template="email:{to}:{subject}:{date}",
            audit_policy=AuditPolicy(
                log_input=True, log_output=True, log_duration=True, pii_fields=["to"]
            ),
        )

        assert contract.capability_key == "send_email"
        assert contract.input_schema["type"] == "object"
        assert contract.retry_policy.max_retries == 3
        assert contract.fallback_policy.fallback_capability == "send_email_backup"

    def test_unhappy_path_invalid_capability_key_empty(self):
        """Unhappy path: Lege capability_key moet falen."""
        with pytest.raises(ValidationError) as exc_info:
            CapabilityContract(
                capability_key="", input_schema={"type": "object"}, output_schema={"type": "object"}
            )

        assert "capability_key" in str(exc_info.value)

    def test_unhappy_path_invalid_capability_key_format(self):
        """Unhappy path: Capability_key met ongeldige karakters."""
        with pytest.raises(ValidationError) as exc_info:
            CapabilityContract(
                capability_key="send email!",  # Spaties en ! niet toegestaan
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

        assert "capability_key" in str(exc_info.value)

    def test_unhappy_path_invalid_schema_not_object(self):
        """Unhappy path: Schema moet een object zijn."""
        with pytest.raises(ValidationError) as exc_info:
            CapabilityContract(
                capability_key="test_capability",
                input_schema="not_an_object",  # type: ignore[arg-type]  # Moet dict zijn
                output_schema={"type": "object"},
            )

        assert "input_schema" in str(exc_info.value)


class TestCapabilityRegistry:
    """Test suite voor CapabilityRegistry."""

    @pytest.fixture
    def registry(self):
        return CapabilityRegistry()

    @pytest.fixture
    def sample_contract(self):
        return CapabilityContract(
            capability_key="send_notification",
            input_schema={
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "enum": ["email", "sms", "push"]},
                    "recipient": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["channel", "recipient", "message"],
            },
            output_schema={
                "type": "object",
                "properties": {"delivery_id": {"type": "string"}, "status": {"type": "string"}},
            },
        )

    def test_happy_path_register_and_resolve(self, registry, sample_contract):
        """Happy path: Capabiliteit registreren en resolven."""
        # Registreer
        registry.register(sample_contract)

        # Resolve
        resolved = registry.resolve("send_notification")

        assert resolved is not None
        assert resolved.capability_key == "send_notification"

    def test_unhappy_path_resolve_unknown_capability(self, registry):
        """Unhappy path: Onbekende capability resolven -> fout."""
        with pytest.raises(UnknownCapabilityError) as exc_info:
            registry.resolve("unknown_capability_xyz")

        assert "unknown_capability_xyz" in str(exc_info.value)
        assert exc_info.value.capability_key == "unknown_capability_xyz"

    def test_unhappy_path_register_duplicate_capability(self, registry, sample_contract):
        """Unhappy path: Dubbele capability registreren -> overschrijven of fout."""
        registry.register(sample_contract)

        # Probeer opnieuw te registreren
        with pytest.raises(CapabilityValidationError) as exc_info:
            registry.register(sample_contract)

        assert "already registered" in str(exc_info.value).lower()


class TestCapabilityResolver:
    """Test suite voor CapabilityResolver met workflow nodes."""

    @pytest.fixture
    def resolver(self):
        registry = CapabilityRegistry()

        # Registreer test capabilities
        registry.register(
            CapabilityContract(
                capability_key="validate_email",
                input_schema={
                    "type": "object",
                    "properties": {"email": {"type": "string", "format": "email"}},
                    "required": ["email"],
                },
                output_schema={
                    "type": "object",
                    "properties": {"valid": {"type": "boolean"}, "normalized": {"type": "string"}},
                },
            )
        )

        registry.register(
            CapabilityContract(
                capability_key="send_email",
                input_schema={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "format": "email"},
                        "subject": {"type": "string", "maxLength": 200},
                        "body": {"type": "string"},
                    },
                    "required": ["to", "subject"],
                },
                output_schema={"type": "object"},
            )
        )

        return CapabilityResolver(registry)

    def test_happy_path_validate_node_success(self, resolver):
        """Happy path: Geldige node -> validatie slaagt."""
        node = {
            "id": "node_1",
            "capability_key": "send_email",
            "input": {"to": "test@example.com", "subject": "Test Subject", "body": "Test body"},
        }

        result = resolver.validate_node(node)

        assert result.is_valid is True
        assert result.errors == []
        assert result.resolved_capability.capability_key == "send_email"

    def test_unhappy_path_validate_node_unknown_capability(self, resolver):
        """Unhappy path 1: Onbekende capability_key -> duidelijke fout."""
        node = {
            "id": "node_2",
            "capability_key": "nonexistent_capability",
            "input": {"some": "data"},
        }

        result = resolver.validate_node(node)

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "Unknown capability" in result.errors[0]

    def test_unhappy_path_validate_node_schema_mismatch(self, resolver):
        """Unhappy path 2: Schema mismatch -> execute geblokkeerd met foutdetail."""
        node = {
            "id": "node_3",
            "capability_key": "send_email",
            "input": {
                # Mist required field "subject"
                "to": "test@example.com",
                "body": "Test body",
            },
        }

        result = resolver.validate_node(node)

        assert result.is_valid is False
        assert len(result.errors) > 0
        # Moet specifieke schema validatie fout bevatten
        error_msg = " ".join(result.errors)
        assert "subject" in error_msg.lower() or "required" in error_msg.lower()

    def test_unhappy_path_validate_node_missing_required(self, resolver):
        """Unhappy path: Mist meerdere required fields."""
        node = {
            "id": "node_4",
            "capability_key": "send_email",
            "input": {
                # Helemaal geen required fields
                "body": "Test body only"
            },
        }

        result = resolver.validate_node(node)

        assert result.is_valid is False
        error_msg = " ".join(result.errors)
        assert "subject" in error_msg.lower() or "required" in error_msg.lower()


class TestCapabilityExecution:
    """Test suite voor capability execution met policies."""

    @pytest.fixture
    def resolver_with_policies(self):
        registry = CapabilityRegistry()

        registry.register(
            CapabilityContract(
                capability_key="process_payment",
                input_schema={
                    "type": "object",
                    "properties": {
                        "amount": {"type": "number", "minimum": 0.01},
                        "currency": {"type": "string", "enum": ["EUR", "USD"]},
                        "customer_id": {"type": "string"},
                    },
                    "required": ["amount", "currency"],
                },
                output_schema={"type": "object"},
                retry_policy=RetryPolicy(
                    max_retries=3,
                    backoff_strategy="exponential",
                    retry_on=["timeout", "rate_limit"],
                ),
                fallback_policy=FallbackPolicy(
                    fallback_capability="process_payment_manual",
                    on_failure_types=["provider_unavailable"],
                ),
            )
        )

        return CapabilityResolver(registry)

    def test_happy_path_get_retry_policy(self, resolver_with_policies):
        """Happy path: Retry policy correct opgehaald."""
        node = {
            "id": "payment_node",
            "capability_key": "process_payment",
            "input": {"amount": 100.00, "currency": "EUR", "customer_id": "cust_123"},
        }

        result = resolver_with_policies.validate_node(node)

        assert result.is_valid is True
        assert result.resolved_capability is not None
        assert result.resolved_capability.retry_policy.max_retries == 3
        assert result.resolved_capability.retry_policy.backoff_strategy == "exponential"

    def test_happy_path_get_fallback_policy(self, resolver_with_policies):
        """Happy path: Fallback policy correct opgehaald."""
        node = {
            "id": "payment_node",
            "capability_key": "process_payment",
            "input": {"amount": 100.00, "currency": "EUR"},
        }

        result = resolver_with_policies.validate_node(node)

        assert result.is_valid is True
        assert result.resolved_capability is not None
        assert (
            result.resolved_capability.fallback_policy.fallback_capability
            == "process_payment_manual"
        )
        assert "provider_unavailable" in result.resolved_capability.fallback_policy.on_failure_types


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
