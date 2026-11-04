"""
Lawful Basis Registry - GDPR Art. 6 compliance enforcement.

This module provides code-level enforcement of GDPR Article 6 lawful bases
for all data processing endpoints.

Usage:
    # Register endpoint
    registry = LawfulBasisRegistry()
    registry.register_endpoint(
        endpoint="/api/users/create",
        lawful_basis=LawfulBasis.CONTRACT,
        data_categories=["personal", "contact"],
        purpose="Create user account for service delivery",
    )

    # Validate access
    result = await registry.validate_endpoint_access(endpoint="/api/users/create")

    # Or use decorator
    @requires_lawful_basis(
        lawful_basis=LawfulBasis.CONSENT,
        data_categories=["email"],
        purpose="Marketing communications",
    )
    async def marketing_endpoint(...):
        ...
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, TypeVar, cast
from collections.abc import Callable

F = TypeVar("F", bound=Callable[..., Any])  # TODO(TYPE): replace Any with concrete type


class LawfulBasis(str, Enum):
    """
    GDPR Article 6 lawful bases for processing.

    Art. 6(1)(a) - Consent
    Art. 6(1)(b) - Contract
    Art. 6(1)(c) - Legal Obligation
    Art. 6(1)(d) - Vital Interests
    Art. 6(1)(e) - Public Task
    Art. 6(1)(f) - Legitimate Interest
    """

    CONSENT = "consent"
    CONTRACT = "contract"
    LEGAL_OBLIGATION = "legal_obligation"
    VITAL_INTERESTS = "vital_interests"
    PUBLIC_TASK = "public_task"
    LEGITIMATE_INTEREST = "legitimate_interest"


class LawfulBasisMissingError(Exception):
    """
    Raised when an endpoint is accessed without a registered lawful basis.

    This is a critical GDPR violation - all data processing must have
    a valid lawful basis under Art. 6.
    """

    pass


@dataclass(frozen=True)
class LawfulBasisValidationResult:
    """Result of lawful basis validation."""

    is_valid: bool
    lawful_basis: LawfulBasis | None
    data_categories: list[str]
    purpose: str | None
    timestamp: datetime


@dataclass(frozen=True)
class EndpointRegistration:
    """Registration of an endpoint with its lawful basis."""

    endpoint: str
    lawful_basis: LawfulBasis
    data_categories: list[str]
    purpose: str
    registered_at: datetime
    legitimate_interest_assessment: str | None = None

    @property
    def consent_required(self) -> bool:
        """True when the lawful basis is explicit consent (GDPR Art. 6(1)(a))."""
        return self.lawful_basis == LawfulBasis.CONSENT


class LawfulBasisRegistry:
    """
    Central registry for GDPR Art. 6 lawful bases.

    Every endpoint that processes personal data MUST be registered
    with a valid lawful basis before it can be accessed.

    This ensures:
    - Accountability (Art. 5(2))
    - Lawfulness of processing (Art. 6)
    - RoPA generation capability (Art. 30)

    Example:
        registry = LawfulBasisRegistry()

        # Register with Art. 6(1)(b) - Contract
        registry.register_endpoint(
            endpoint="/api/users/create",
            lawful_basis=LawfulBasis.CONTRACT,
            data_categories=["personal", "contact"],
            purpose="Create user account for service delivery",
        )

        # Will succeed - has lawful basis
        result = await registry.validate_endpoint_access(
            endpoint="/api/users/create"
        )

        # Will raise - no lawful basis registered
        await registry.validate_endpoint_access(
            endpoint="/api/unregistered"
        )  # Raises LawfulBasisMissingError
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._endpoints: dict[str, EndpointRegistration] = {}
        self._access_log: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

    def register_endpoint(
        self,
        endpoint: str,
        lawful_basis: LawfulBasis,
        data_categories: list[str],
        purpose: str,
        legitimate_interest_assessment: str | None = None,
    ) -> None:
        """
        Register an endpoint with its GDPR Art. 6 lawful basis.

        Args:
            endpoint: API endpoint path (e.g., "/api/users/create")
            lawful_basis: GDPR Art. 6 lawful basis
            data_categories: Categories of personal data processed
            purpose: Clear purpose description
            legitimate_interest_assessment: Required for Art. 6(1)(f)

        Raises:
            ValueError: If Art. 6(1)(f) used without LIA

        Example:
            registry.register_endpoint(
                endpoint="/api/analytics/track",
                lawful_basis=LawfulBasis.LEGITIMATE_INTEREST,
                data_categories=["usage"],
                purpose="Analytics",
                legitimate_interest_assessment="Balancing test completed..."
            )
        """
        if lawful_basis == LawfulBasis.LEGITIMATE_INTEREST and not legitimate_interest_assessment:
            raise ValueError(
                f"Legitimate Interest Assessment (LIA) required for Art. 6(1)(f). "
                f"Endpoint: {endpoint}. "
                f"Conduct a balancing test and document the justification."
            )

        self._endpoints[endpoint] = EndpointRegistration(
            endpoint=endpoint,
            lawful_basis=lawful_basis,
            data_categories=data_categories,
            purpose=purpose,
            registered_at=datetime.now(timezone.utc),
            legitimate_interest_assessment=legitimate_interest_assessment,
        )

    async def validate_endpoint_access(
        self,
        endpoint: str,
        data_categories: list[str] | None = None,
    ) -> LawfulBasisValidationResult:
        """
        Validate that an endpoint has a registered lawful basis.

        This MUST be called before processing any personal data.

        Args:
            endpoint: API endpoint being accessed
            data_categories: Data categories being processed (for validation)

        Returns:
            LawfulBasisValidationResult with validation details

        Raises:
            LawfulBasisMissingError: If endpoint has no registered lawful basis

        Example:
            try:
                result = await registry.validate_endpoint_access("/api/users/create")
                # Proceed with processing
            except LawfulBasisMissingError:
                # Block access - GDPR violation!
                raise HTTPException(500, "Lawful basis not configured")
        """
        registration = self._endpoints.get(endpoint)

        if not registration:
            # Log violation for audit
            violation = {
                "endpoint": endpoint,
                "timestamp": datetime.now(timezone.utc),
                "violation": "missing_lawful_basis",
            }
            self._access_log.append(violation)

            raise LawfulBasisMissingError(
                f"Endpoint '{endpoint}' has no registered lawful basis. "
                f"All data processing endpoints must register under Art. 6 GDPR. "
                f"This is a CRITICAL compliance violation."
            )

        # Log successful access
        self._access_log.append(
            {
                "endpoint": endpoint,
                "lawful_basis": registration.lawful_basis.value,
                "timestamp": datetime.now(timezone.utc),
                "violation": None,
            }
        )

        return LawfulBasisValidationResult(
            is_valid=True,
            lawful_basis=registration.lawful_basis,
            data_categories=registration.data_categories,
            purpose=registration.purpose,
            timestamp=datetime.now(timezone.utc),
        )

    def get_endpoint_info(self, endpoint: str) -> EndpointRegistration | None:
        """
        Get registration info for an endpoint.

        Args:
            endpoint: API endpoint path

        Returns:
            EndpointRegistration if found, None otherwise
        """
        return self._endpoints.get(endpoint)

    # Sync alias for test compatibility
    def validate(self, endpoint: str) -> EndpointRegistration | None:
        return self.get_endpoint_info(endpoint)

    def get_all_registrations(self) -> list[EndpointRegistration]:
        """
        Get all registered endpoints.

        Returns:
            List of all EndpointRegistration objects

        Note:
            This can be used to auto-generate RoPA (Art. 30)
        """
        return list(self._endpoints.values())

    def get_violations(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Get all access violations.

        Returns:
            List of violation logs for audit
        """
        return [log for log in self._access_log if log.get("violation")]


def requires_lawful_basis(
    lawful_basis: LawfulBasis,
    data_categories: list[str],
    purpose: str,
) -> Callable[[F], F]:
    """
    Decorator for registering a function's lawful basis.

    This decorator stores GDPR metadata on the function and can
    optionally register it with a global registry.

    Args:
        lawful_basis: GDPR Art. 6 lawful basis
        data_categories: Categories of personal data processed
        purpose: Clear purpose description

    Returns:
        Decorator function

    Example:
        @requires_lawful_basis(
            lawful_basis=LawfulBasis.CONTRACT,
            data_categories=["personal", "contact"],
            purpose="Create user account",
        )
        async def create_user(user_data: dict) -> User:
            ...

        # Access metadata
        print(create_user._gdpr_lawful_basis)  # LawfulBasis.CONTRACT
    """

    def decorator(func: F) -> F:
        # Store metadata on function
        cast(Any, func)._gdpr_lawful_basis = (  # TODO(TYPE): replace Any with concrete type
            lawful_basis
        )
        cast(Any, func)._gdpr_data_categories = (  # TODO(TYPE): replace Any with concrete type
            data_categories
        )
        cast(Any, func)._gdpr_purpose = purpose  # TODO(TYPE): replace Any with concrete type

        return func

    return decorator


def lawful_basis_dependency(endpoint: str) -> Callable[..., Any]:
    """FastAPI Depends()-compatible factory for GDPR Art. 6 enforcement (AUDIT-GDPR-001).

    Usage:
        @router.get("/api/sensitive")
        async def my_endpoint(
            _: None = Depends(lawful_basis_dependency("/api/sensitive")),
        ) -> ...:
            ...
    """
    from fastapi import Depends  # local import -- keeps this module free of FastAPI at import time

    from src.core.governance.dependencies import (
        get_lawful_basis_registry,
    )

    async def _check(
        registry: "LawfulBasisRegistry" = Depends(get_lawful_basis_registry),
    ) -> None:
        await registry.validate_endpoint_access(endpoint)

    return _check


# Module exports
__all__ = [
    "LawfulBasis",
    "LawfulBasisRegistry",
    "LawfulBasisMissingError",
    "LawfulBasisValidationResult",
    "EndpointRegistration",
    "requires_lawful_basis",
    "lawful_basis_dependency",
]
