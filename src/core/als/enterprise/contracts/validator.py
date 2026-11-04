"""
Contract Validator - Payload and schema validation for A2A contracts.

Implements the hard validation rules defined in Section 0.2 and 1.2
of the ALS 2.0 specification.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from src.core.als.enterprise.contracts.models import A2AContract
from src.core.als.enterprise.contracts.schema_registry import (
    DataSchema,
    SchemaRegistry,
    SemVer,
)


class ValidationError(Exception):
    """Raised when contract validation fails"""

    pass


class SchemaMismatchError(ValidationError):
    """Raised when schema hash or structure doesn't match"""

    pass


class DeadlineExceededError(ValidationError):
    """Raised when contract deadline is exceeded"""

    pass


class InsufficientPranaError(ValidationError):
    """Raised when department has insufficient prana budget"""

    pass


@dataclass
class ValidationResult:
    """Result of contract validation"""

    is_valid: bool
    errors: list[str]
    validation_time_ms: int
    schema_valid: bool = False
    deadline_valid: bool = False
    prana_valid: bool = False
    payload_hash: str | None = None

    def __post_init__(self) -> None:
        if not self.errors:
            self.errors = []


class ContractValidator:
    """
    Validates A2A contracts against schemas, deadlines, and budgets.

    NON-NEGOTIABLE VALIDATIONS:
    1. Schema hash MUST match (SchemaMismatchError if not)
    2. All required fields MUST be present
    3. Types MUST match JSON Schema
    4. Deadline MUST not be exceeded
    5. Prana budget MUST be sufficient
    """

    def __init__(self, schema_registry: SchemaRegistry) -> None:
        self.schema_registry = schema_registry

    def validate_contract(
        self, contract: A2AContract, payload: dict[str, Any], available_prana: int  # TODO(TYPE): replace Any with concrete type
    ) -> ValidationResult:
        """
        Validate contract execution request.

        Args:
            contract: The A2A contract
            payload: Input payload to validate
            available_prana: Department's available prana budget

        Returns:
            ValidationResult with detailed status
        """
        start_time = datetime.now(timezone.utc)
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # 1. Schema validation (HARD REQUIREMENT)
        schema_valid, schema_error = self._validate_schema(contract, payload)
        if not schema_valid:
            errors.append(f"Schema validation failed: {schema_error}")

        # 2. Deadline validation
        deadline_valid, deadline_error = self._validate_deadline(contract)
        if not deadline_valid:
            errors.append(f"Deadline validation failed: {deadline_error}")

        # 3. Prana validation
        prana_valid, prana_error = self._validate_prana(contract, available_prana)
        if not prana_valid:
            errors.append(f"Prana validation failed: {prana_error}")

        # Compute payload hash (for audit, no PII)
        payload_hash = self._compute_payload_hash(payload)

        # Calculate validation time
        end_time = datetime.now(timezone.utc)
        validation_time_ms = int((end_time - start_time).total_seconds() * 1000)

        is_valid = schema_valid and deadline_valid and prana_valid

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            validation_time_ms=validation_time_ms,
            schema_valid=schema_valid,
            deadline_valid=deadline_valid,
            prana_valid=prana_valid,
            payload_hash=payload_hash,
        )

    def _validate_schema(
        self, contract: A2AContract, payload: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[bool, str | None]:
        """
        Validate payload against contract schema.

        HARD RULES:
        1. Schema hash MUST match contract.schema_hash
        2. All required fields MUST be present
        3. Types MUST match JSON Schema
        """
        # Get schema from registry
        schema = self.schema_registry.get(contract.schema_ref.ref)
        if schema is None:
            return False, f"Schema {contract.schema_ref.ref} not found in registry"

        # 1. Verify schema hash (CRITICAL - prevents schema tampering)
        computed_hash = schema.compute_hash()
        if computed_hash != contract.schema_hash:
            return False, (
                f"Schema hash mismatch: contract has {contract.schema_hash}, "
                f"computed {computed_hash}. Schema may have been modified."
            )

        # 2. Validate payload against schema
        is_valid, error = schema.validate_payload(payload)
        if not is_valid:
            return False, error

        return True, None

    def _validate_deadline(self, contract: A2AContract) -> tuple[bool, str | None]:
        """
        Validate contract deadline.

        NOTE: This checks if deadline has been exceeded during execution.
        The deadline_ms is from agreement to settlement.
        """
        if contract.agreed_at is None:
            return False, "Contract not yet agreed"

        elapsed_ms = (datetime.now(timezone.utc) - contract.agreed_at).total_seconds() * 1000

        if elapsed_ms > contract.deadline_ms:
            return False, (
                f"Deadline exceeded: {elapsed_ms:.0f}ms elapsed, "
                f"{contract.deadline_ms}ms allowed"
            )

        return True, None

    def _validate_prana(
        self, contract: A2AContract, available_prana: int
    ) -> tuple[bool, str | None]:
        """
        Validate prana budget.

        HARD RULE: If prana < cost, reject immediately
        """
        if available_prana < contract.prana_cost:
            return False, (
                f"Insufficient prana: {available_prana} available, "
                f"{contract.prana_cost} required"
            )

        return True, None

    def _compute_payload_hash(self, payload: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """
        Compute canonical SHA-256 hash of payload.

        Used for audit trails (stores hash, not actual PII data).
        """
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]

    def validate_idempotency(
        self, idempotency_key: str, processed_keys: set[Any]  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[bool, str | None]:
        """
        Validate idempotency key.

        NON-NEGOTIABLE: Same idempotency key = same result, no duplicate side effects
        """
        if idempotency_key in processed_keys:
            return False, f"Idempotency key {idempotency_key} already processed"
        return True, None


class SchemaCompatibilityChecker:
    """
    Checks compatibility between producer and consumer schemas.
    """

    @staticmethod
    def check_compatibility(
        producer_schema: DataSchema, consumer_version: str
    ) -> tuple[bool, list[str]]:
        """
        Check if producer schema is compatible with consumer version.

        Returns:
            (is_compatible, list_of_incompatibilities)
        """
        issues: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        try:
            consumer_semver = SemVer.parse(consumer_version)
        except ValueError as e:
            return False, [f"Invalid consumer version: {e}"]

        producer_version = producer_schema.schema_ref.version

        # Major version MUST match
        if producer_version.major != consumer_semver.major:
            issues.append(
                f"Major version mismatch: producer {producer_version.major}.x, "
                f"consumer {consumer_semver.major}.x"
            )

        # Producer minor >= consumer minor
        if producer_version.minor < consumer_semver.minor:
            issues.append(
                f"Producer minor version ({producer_version.minor}) < "
                f"consumer minor ({consumer_semver.minor}). "
                f"Producer missing features consumer expects."
            )

        # Check for deprecated fields
        if producer_schema.deprecated_fields:
            issues.append(
                f"Producer schema has deprecated fields: " f"{producer_schema.deprecated_fields}"
            )

        return len(issues) == 0, issues
