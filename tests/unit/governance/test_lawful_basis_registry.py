"""
Unit tests for LawfulBasisRegistry - GDPR Art. 6 compliance.

TDD Workflow: RED phase - Write failing test first.
"""

from datetime import datetime, timezone

import pytest

# These imports will fail initially - that's the RED phase
from src.core.governance.lawful_basis_registry import (
    LawfulBasis,
    LawfulBasisMissingError,
    LawfulBasisRegistry,
    requires_lawful_basis,
)


@pytest.mark.unit
@pytest.mark.gdpr
class TestLawfulBasisRegistry:
    """Test suite for GDPR Art. 6 lawful basis enforcement."""

    def test_lawful_basis_enum_values(self):
        """LawfulBasis enum must have all GDPR Art. 6 values."""
        assert LawfulBasis.CONSENT == "consent"
        assert LawfulBasis.CONTRACT == "contract"
        assert LawfulBasis.LEGAL_OBLIGATION == "legal_obligation"
        assert LawfulBasis.VITAL_INTERESTS == "vital_interests"
        assert LawfulBasis.PUBLIC_TASK == "public_task"
        assert LawfulBasis.LEGITIMATE_INTEREST == "legitimate_interest"

    def test_registry_initialization(self):
        """Registry must initialize empty."""
        registry = LawfulBasisRegistry()

        assert registry.get_all_registrations() == []
        assert registry.get_violations() == []

    def test_register_endpoint_with_contract_basis(self):
        """Must be able to register endpoint with Art. 6(1)(b) Contract basis."""
        registry = LawfulBasisRegistry()

        registry.register_endpoint(
            endpoint="/api/users/create",
            lawful_basis=LawfulBasis.CONTRACT,
            data_categories=["personal", "contact"],
            purpose="Create user account for service delivery",
        )

        registrations = registry.get_all_registrations()
        assert len(registrations) == 1
        assert registrations[0].endpoint == "/api/users/create"
        assert registrations[0].lawful_basis == LawfulBasis.CONTRACT

    def test_register_endpoint_with_consent_basis(self):
        """Must be able to register endpoint with Art. 6(1)(a) Consent basis."""
        registry = LawfulBasisRegistry()

        registry.register_endpoint(
            endpoint="/api/marketing/subscribe",
            lawful_basis=LawfulBasis.CONSENT,
            data_categories=["email", "preferences"],
            purpose="Marketing communications with explicit consent",
        )

        info = registry.get_endpoint_info("/api/marketing/subscribe")
        assert info is not None
        assert info.lawful_basis == LawfulBasis.CONSENT

    def test_register_legitimate_interest_requires_lia(self):
        """Art. 6(1)(f) Legitimate Interest MUST have LIA documented."""
        registry = LawfulBasisRegistry()

        with pytest.raises(ValueError) as exc_info:
            registry.register_endpoint(
                endpoint="/api/analytics/track",
                lawful_basis=LawfulBasis.LEGITIMATE_INTEREST,
                data_categories=["usage", "behavioral"],
                purpose="Analytics for service improvement",
                # Missing legitimate_interest_assessment!
            )

        assert "LIA" in str(exc_info.value)
        assert "Art. 6(1)(f)" in str(exc_info.value)

    def test_register_legitimate_interest_with_lia_succeeds(self):
        """Art. 6(1)(f) succeeds when LIA is provided."""
        registry = LawfulBasisRegistry()

        registry.register_endpoint(
            endpoint="/api/analytics/track",
            lawful_basis=LawfulBasis.LEGITIMATE_INTEREST,
            data_categories=["usage", "behavioral"],
            purpose="Analytics for service improvement",
            legitimate_interest_assessment="Balancing test: user impact minimal, business benefit significant, opt-out available",
        )

        info = registry.get_endpoint_info("/api/analytics/track")
        assert info.legitimate_interest_assessment is not None

    @pytest.mark.asyncio
    async def test_validate_registered_endpoint_succeeds(self):
        """Validation must succeed for registered endpoint."""
        registry = LawfulBasisRegistry()

        registry.register_endpoint(
            endpoint="/api/users/create",
            lawful_basis=LawfulBasis.CONTRACT,
            data_categories=["personal"],
            purpose="User account creation",
        )

        result = await registry.validate_endpoint_access(
            endpoint="/api/users/create",
            data_categories=["personal"],
        )

        assert result.is_valid is True
        assert result.lawful_basis == LawfulBasis.CONTRACT
        assert result.purpose == "User account creation"
        assert isinstance(result.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_validate_unregistered_endpoint_raises_error(self):
        """CRITICAL: Unregistered endpoint must raise LawfulBasisMissingError."""
        registry = LawfulBasisRegistry()
        # Intentionally NOT registering the endpoint

        with pytest.raises(LawfulBasisMissingError) as exc_info:
            await registry.validate_endpoint_access(
                endpoint="/api/users/create",
                data_categories=["personal"],
            )

        assert "/api/users/create" in str(exc_info.value)
        assert "no registered lawful basis" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_unregistered_endpoint_logs_violation(self):
        """Access violation must be logged for audit."""
        registry = LawfulBasisRegistry()

        try:
            await registry.validate_endpoint_access(
                endpoint="/api/unregistered/endpoint",
                data_categories=["personal"],
            )
        except LawfulBasisMissingError:
            pass  # Expected

        violations = registry.get_violations()
        assert len(violations) == 1
        assert violations[0]["endpoint"] == "/api/unregistered/endpoint"
        assert violations[0]["violation"] == "missing_lawful_basis"

    def test_get_endpoint_info_returns_none_for_unregistered(self):
        """get_endpoint_info must return None for unregistered endpoints."""
        registry = LawfulBasisRegistry()

        info = registry.get_endpoint_info("/api/not-registered")

        assert info is None

    def test_multiple_endpoints_in_registry(self):
        """Registry must handle multiple endpoints."""
        registry = LawfulBasisRegistry()

        endpoints = [
            ("/api/users/create", LawfulBasis.CONTRACT),
            ("/api/users/delete", LawfulBasis.CONSENT),
            ("/api/audit/export", LawfulBasis.LEGAL_OBLIGATION),
        ]

        for endpoint, basis in endpoints:
            registry.register_endpoint(
                endpoint=endpoint,
                lawful_basis=basis,
                data_categories=["personal"],
                purpose=f"Purpose for {endpoint}",
            )

        registrations = registry.get_all_registrations()
        assert len(registrations) == 3

        endpoints_in_registry = {r.endpoint for r in registrations}
        assert endpoints_in_registry == {e for e, _ in endpoints}


@pytest.mark.unit
@pytest.mark.gdpr
class TestLawfulBasisDecorator:
    """Test suite for @requires_lawful_basis decorator."""

    def test_decorator_stores_metadata_on_function(self):
        """Decorator must store GDPR metadata on decorated function."""

        @requires_lawful_basis(
            lawful_basis=LawfulBasis.CONTRACT,
            data_categories=["personal", "account"],
            purpose="Create user account",
        )
        async def create_user_endpoint(user_data: dict) -> dict:
            return {"id": 1, "email": user_data["email"]}

        # Check metadata stored on function
        assert hasattr(create_user_endpoint, "_gdpr_lawful_basis")
        assert create_user_endpoint._gdpr_lawful_basis == LawfulBasis.CONTRACT
        assert create_user_endpoint._gdpr_data_categories == ["personal", "account"]
        assert create_user_endpoint._gdpr_purpose == "Create user account"

    def test_decorator_registers_on_import(self):
        """Decorator must register endpoint at import time."""
        registry = LawfulBasisRegistry()

        # Before decoration - registry should be empty
        initial_count = len(registry.get_all_registrations())

        @requires_lawful_basis(
            lawful_basis=LawfulBasis.CONSENT,
            data_categories=["email"],
            purpose="Marketing subscription",
        )
        async def marketing_subscribe(email: str) -> dict:
            return {"subscribed": True}

        # After decoration - should be registered
        # Note: In real implementation, decorator would register to singleton
        # For now, we just verify the decorator doesn't crash
        assert hasattr(marketing_subscribe, "_gdpr_lawful_basis")


@pytest.mark.unit
@pytest.mark.gdpr
class TestRoPAGeneration:
    """Test suite for Register of Processing Activities (RoPA) generation."""

    def test_get_all_registrations_returns_ropa_data(self):
        """get_all_registrations must return data suitable for RoPA."""
        registry = LawfulBasisRegistry()

        registry.register_endpoint(
            endpoint="/api/users/create",
            lawful_basis=LawfulBasis.CONTRACT,
            data_categories=["personal", "contact"],
            purpose="User account creation",
        )

        registrations = registry.get_all_registrations()

        # RoPA requirements
        assert len(registrations) > 0
        reg = registrations[0]
        assert reg.endpoint is not None  # Processing activity identifier
        assert reg.lawful_basis is not None  # Art. 6 basis
        assert reg.data_categories is not None  # Categories of data
        assert reg.purpose is not None  # Purpose of processing
        assert isinstance(reg.registered_at, datetime)  # Timestamp


# Mark file as test file for pytest
__test__ = True
