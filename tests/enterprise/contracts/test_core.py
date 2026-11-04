"""
Sprint A Tests - Contract Core

Tests for:
- SchemaRef parsing
- SemVer compatibility
- Contract state machine transitions
- Payload validation with hash checking
"""

import hashlib
import json
from datetime import datetime, timezone

import pytest

from src.core.als.enterprise.contracts.models import (
    A2AContract,
    ContractState,
    ContractTransitionError,
)
from src.core.als.enterprise.contracts.schema_registry import (
    DataSchema,
    DuplicateSchemaError,
    SchemaIntegrityError,
    SchemaRef,
    SchemaRegistry,
    SemVer,
)
from src.core.als.enterprise.contracts.state_machine import ActorRole, ContractStateMachine
from src.core.als.enterprise.contracts.validator import ContractValidator, ValidationError
from src.core.als.enterprise.departments.department_orchestrator import Department


class TestSemVer:
    """Test semantic versioning"""

    def test_semver_parsing(self):
        """SemVer correctly stores major, minor, patch"""
        v = SemVer(major=1, minor=2, patch=3)
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_semver_string(self):
        """SemVer converts to string correctly"""
        v = SemVer(major=1, minor=2, patch=3)
        assert str(v) == "1.2.3"

    def test_semver_equality(self):
        """SemVers with same values are equal"""
        v1 = SemVer(major=1, minor=2, patch=3)
        v2 = SemVer(major=1, minor=2, patch=3)
        assert v1 == v2

    def test_backward_compatibility_minor(self):
        """Producer minor >= consumer minor is compatible"""
        consumer = SemVer(major=1, minor=2, patch=0)
        producer = SemVer(major=1, minor=3, patch=0)
        assert producer.is_compatible_with(consumer)

    def test_backward_compatibility_same(self):
        """Same version is compatible"""
        consumer = SemVer(major=1, minor=2, patch=0)
        producer = SemVer(major=1, minor=2, patch=0)
        assert producer.is_compatible_with(consumer)

    def test_backward_incompatibility_major(self):
        """Different major versions are incompatible"""
        consumer = SemVer(major=1, minor=2, patch=0)
        producer = SemVer(major=2, minor=0, patch=0)
        assert not producer.is_compatible_with(consumer)

    def test_backward_incompatibility_lower_minor(self):
        """Producer minor < consumer minor is incompatible"""
        consumer = SemVer(major=1, minor=3, patch=0)
        producer = SemVer(major=1, minor=2, patch=0)
        assert not producer.is_compatible_with(consumer)

    def test_newer_than(self):
        """SemVer correctly compares versions"""
        v1 = SemVer(major=1, minor=2, patch=0)
        v2 = SemVer(major=1, minor=3, patch=0)
        assert v2.is_newer_than(v1)
        assert not v1.is_newer_than(v2)


class TestSchemaRef:
    """Test schema reference parsing"""

    def test_schema_ref_parsing(self):
        """Parse 'hr.skill_matrix@1.2.0' correctly"""
        ref = SchemaRef.parse("hr.skill_matrix@1.2.0")
        assert ref.domain == "hr"
        assert ref.name == "skill_matrix"
        assert ref.version.major == 1
        assert ref.version.minor == 2
        assert ref.version.patch == 0

    def test_schema_ref_with_patch(self):
        """Parse version with patch number"""
        ref = SchemaRef.parse("finance.metrics@2.1.3")
        assert ref.domain == "finance"
        assert ref.name == "metrics"
        assert ref.version == SemVer(major=2, minor=1, patch=3)

    def test_schema_ref_ref_property(self):
        """ref property returns canonical format"""
        ref = SchemaRef.parse("hr.skill_matrix@1.2.0")
        assert ref.ref == "hr.skill_matrix@1.2.0"

    def test_invalid_format_no_at(self):
        """Missing @ raises ValueError"""
        with pytest.raises(ValueError) as exc_info:
            SchemaRef.parse("hr.skill_matrix")
        assert "Invalid schema ref format" in str(exc_info.value)

    def test_invalid_version_format(self):
        """Invalid version format raises ValueError"""
        with pytest.raises(ValueError):
            SchemaRef.parse("hr.skill_matrix@1.2.3.4")


class TestDataSchema:
    """Test data schema validation"""

    def create_test_schema(self, schema_hash: str = None) -> DataSchema:
        """Helper to create a test schema"""
        json_schema = {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
        }

        # Compute actual hash
        canonical = json.dumps(json_schema, sort_keys=True, separators=(",", ":"))
        computed_hash = hashlib.sha256(canonical.encode()).hexdigest()[:32]

        return DataSchema(
            schema_ref=SchemaRef.parse("hr.employee@1.0.0"),
            json_schema=json_schema,
            required_fields=["employee_id", "name"],
            schema_hash=schema_hash or computed_hash,
            created_at="2024-01-01T00:00:00Z",
            created_by="test",
        )

    def test_hash_computation(self):
        """Schema computes hash correctly"""
        schema = self.create_test_schema()
        computed = schema.compute_hash()
        assert len(computed) == 32  # SHA-256 truncated to 32 chars

    def test_hash_mismatch_raises_error(self):
        """Hash mismatch raises SchemaIntegrityError"""
        with pytest.raises(SchemaIntegrityError) as exc_info:
            self.create_test_schema(schema_hash="wrong_hash")
        assert "Schema hash mismatch" in str(exc_info.value)

    def test_payload_validation_success(self):
        """Valid payload passes validation"""
        schema = self.create_test_schema()
        payload = {"employee_id": "123", "name": "John", "age": 30}

        is_valid, error = schema.validate_payload(payload)
        assert is_valid is True
        assert error is None

    def test_payload_validation_missing_required(self):
        """Missing required field fails validation"""
        schema = self.create_test_schema()
        payload = {"name": "John"}  # Missing employee_id

        is_valid, error = schema.validate_payload(payload)
        assert is_valid is False
        assert "employee_id" in error

    def test_payload_validation_type_mismatch(self):
        """Type mismatch fails validation"""
        schema = self.create_test_schema()
        payload = {"employee_id": "123", "name": "John", "age": "not_an_int"}

        is_valid, error = schema.validate_payload(payload)
        assert is_valid is False
        assert "age" in error


class TestSchemaRegistry:
    """Test schema registry operations"""

    def test_register_schema(self):
        """Schema can be registered"""
        registry = SchemaRegistry()
        json_schema = {"type": "object"}
        canonical = json.dumps(json_schema, sort_keys=True, separators=(",", ":"))
        computed_hash = hashlib.sha256(canonical.encode()).hexdigest()[:32]

        schema = DataSchema(
            schema_ref=SchemaRef.parse("hr.test@1.0.0"),
            json_schema=json_schema,
            required_fields=[],
            schema_hash=computed_hash,
            created_at="2024-01-01T00:00:00Z",
            created_by="test",
        )

        registry.register(schema)
        retrieved = registry.get("hr.test@1.0.0")
        assert retrieved == schema

    def test_duplicate_registration_raises_error(self):
        """Duplicate schema raises DuplicateSchemaError (HTTP 409)"""
        registry = SchemaRegistry()
        json_schema = {"type": "object"}
        canonical = json.dumps(json_schema, sort_keys=True, separators=(",", ":"))
        computed_hash = hashlib.sha256(canonical.encode()).hexdigest()[:32]

        schema = DataSchema(
            schema_ref=SchemaRef.parse("hr.test@1.0.0"),
            json_schema=json_schema,
            required_fields=[],
            schema_hash=computed_hash,
            created_at="2024-01-01T00:00:00Z",
            created_by="test",
        )

        registry.register(schema)

        with pytest.raises(DuplicateSchemaError) as exc_info:
            registry.register(schema)
        assert "409" in str(exc_info.value)

    def test_get_compatible_schema(self):
        """Get newest compatible schema version"""
        registry = SchemaRegistry()

        # Register v1.0.0 and v1.1.0
        json_schema_v1 = {"type": "object", "version": "1"}
        canonical_v1 = json.dumps(json_schema_v1, sort_keys=True, separators=(",", ":"))
        hash_v1 = hashlib.sha256(canonical_v1.encode()).hexdigest()[:32]

        json_schema_v1_1 = {"type": "object", "version": "1.1"}
        canonical_v1_1 = json.dumps(json_schema_v1_1, sort_keys=True, separators=(",", ":"))
        hash_v1_1 = hashlib.sha256(canonical_v1_1.encode()).hexdigest()[:32]

        schema_v1 = DataSchema(
            schema_ref=SchemaRef.parse("hr.test@1.0.0"),
            json_schema=json_schema_v1,
            required_fields=[],
            schema_hash=hash_v1,
            created_at="2024-01-01T00:00:00Z",
            created_by="test",
        )
        schema_v1_1 = DataSchema(
            schema_ref=SchemaRef.parse("hr.test@1.1.0"),
            json_schema=json_schema_v1_1,
            required_fields=[],
            schema_hash=hash_v1_1,
            created_at="2024-01-01T00:00:00Z",
            created_by="test",
        )

        registry.register(schema_v1)
        registry.register(schema_v1_1)

        # Consumer at v1.0.0 should get v1.1.0
        consumer_version = SemVer(major=1, minor=0, patch=0)
        compatible = registry.get_compatible("hr", "test", consumer_version)

        assert compatible is not None
        assert compatible.schema_ref.version.minor == 1


class TestContractStateMachine:
    """Test contract state transitions"""

    def test_proposed_to_agreed_allowed(self):
        """PROPOSED -> AGREED allowed for PRODUCER"""
        assert ContractStateMachine.can_transition(
            ContractState.PROPOSED, ContractState.AGREED, ActorRole.PRODUCER
        )

    def test_proposed_to_rejected_allowed(self):
        """PROPOSED -> REJECTED allowed for CONSUMER"""
        assert ContractStateMachine.can_transition(
            ContractState.PROPOSED, ContractState.REJECTED, ActorRole.CONSUMER
        )

    def test_proposed_to_executing_not_allowed(self):
        """PROPOSED -> EXECUTING is NOT allowed"""
        assert not ContractStateMachine.can_transition(
            ContractState.PROPOSED, ContractState.EXECUTING, ActorRole.SYSTEM
        )

    def test_agreed_to_executing_allowed_for_system(self):
        """AGREED -> EXECUTING allowed for SYSTEM"""
        assert ContractStateMachine.can_transition(
            ContractState.AGREED, ContractState.EXECUTING, ActorRole.SYSTEM
        )

    def test_agreed_to_executing_not_allowed_for_producer(self):
        """AGREED -> EXECUTING NOT allowed for PRODUCER"""
        assert not ContractStateMachine.can_transition(
            ContractState.AGREED, ContractState.EXECUTING, ActorRole.PRODUCER
        )

    def test_invalid_transition_raises_error(self):
        """Invalid transition raises ContractTransitionError"""
        with pytest.raises(ContractTransitionError) as exc_info:
            ContractStateMachine.transition(
                ContractState.PROPOSED, ContractState.EXECUTING, ActorRole.SYSTEM
            )
        assert "Invalid transition" in str(exc_info.value)

    def test_retry_limit_validation(self):
        """Max 3 retries allowed"""
        assert ContractStateMachine.validate_retry(0, max_retries=3)  # First retry
        assert ContractStateMachine.validate_retry(2, max_retries=3)  # Third retry
        assert not ContractStateMachine.validate_retry(
            3, max_retries=3
        )  # Fourth retry - not allowed

    def test_get_allowed_transitions(self):
        """Get list of allowed next states"""
        allowed = ContractStateMachine.get_allowed_transitions(
            ContractState.PROPOSED, ActorRole.PRODUCER
        )
        assert ContractState.AGREED in allowed
        assert ContractState.COUNTERED in allowed


class TestContractValidator:
    """Test contract validation"""

    def create_test_contract(self) -> A2AContract:
        """Helper to create a test contract"""
        return A2AContract(
            contract_id="test_001",
            tenant_id=1,
            producer_agent="producer_1",
            consumer_agent="consumer_1",
            producer_department=Department.FINANCE,
            consumer_department=Department.HR,
            schema_ref=SchemaRef.parse("hr.test@1.0.0"),
            schema_hash="abc123",
            deadline_ms=5000,
            prana_cost=100,
            agreed_at=datetime.now(timezone.utc),  # Set agreed_at for deadline validation
        )

    def test_deadline_exceeded(self):
        """Deadline exceeded fails validation"""
        registry = SchemaRegistry()
        validator = ContractValidator(registry)

        contract = self.create_test_contract()
        contract.agreed_at = datetime(2020, 1, 1, tzinfo=timezone.utc)  # Long ago

        result = validator.validate_contract(contract, payload={}, available_prana=1000)

        assert not result.is_valid
        assert not result.deadline_valid
        assert "Deadline exceeded" in str(result.errors)

    def test_insufficient_prana(self):
        """Insufficient prana fails validation"""
        registry = SchemaRegistry()
        validator = ContractValidator(registry)

        contract = self.create_test_contract()

        result = validator.validate_contract(
            contract,
            payload={},
            available_prana=50,  # Less than required 100
        )

        assert not result.is_valid
        assert not result.prana_valid
        assert "Insufficient prana" in str(result.errors)

    def test_validation_success(self):
        """All validations pass"""
        registry = SchemaRegistry()
        validator = ContractValidator(registry)

        contract = self.create_test_contract()

        result = validator.validate_contract(contract, payload={}, available_prana=100)

        # This will fail schema validation because schema not in registry
        # but deadline and prana should pass
        assert result.deadline_valid
        assert result.prana_valid


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
