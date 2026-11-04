"""
Sprint 3 Slice 2: Contract Validator - RED Phase Tests

Tests for backward compatibility validation of domain pack output contracts.
Prevents breaking changes that would affect downstream consumers.
"""

from typing import Any, Dict
from uuid import uuid4

import pytest

# Tests will import from src.core.procedures.contract_validator
# pytest.mark.asyncio not needed - these are sync validation tests


class TestBackwardCompatibility:
    """Test backward compatibility validation rules"""

    def test_removing_required_field_breaks_compatibility(self):
        """Should detect when a required field is removed (breaking change)"""
        old_contract = {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string"},
                "amount": {"type": "number"},
                "status": {"type": "string"},
            },
            "required": ["invoice_id", "amount", "status"],
        }

        new_contract = {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string"},
                "amount": {"type": "number"},
                # status removed
            },
            "required": ["invoice_id", "amount"],
        }

        from src.core.procedures.contract_validator import ContractValidator

        validator = ContractValidator()
        result = validator.validate_compatibility(old_contract, new_contract)

        assert not result.is_compatible
        assert "removed_required_field" in result.breaking_changes[0]["type"]
        assert result.breaking_changes[0]["field"] == "status"

    def test_changing_field_type_breaks_compatibility(self):
        """Should detect when a field type changes (breaking change)"""
        old_contract = {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string"},
                "amount": {"type": "number"},
            },
            "required": ["invoice_id", "amount"],
        }

        new_contract = {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string"},
                "amount": {"type": "string"},  # Changed from number to string
            },
            "required": ["invoice_id", "amount"],
        }

        from src.core.procedures.contract_validator import ContractValidator

        validator = ContractValidator()
        result = validator.validate_compatibility(old_contract, new_contract)

        assert not result.is_compatible
        assert "field_type_changed" in result.breaking_changes[0]["type"]
        assert result.breaking_changes[0]["field"] == "amount"
        assert result.breaking_changes[0]["old_type"] == "number"
        assert result.breaking_changes[0]["new_type"] == "string"

    def test_adding_optional_field_is_compatible(self):
        """Should allow adding optional fields (non-breaking change)"""
        old_contract = {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string"},
                "amount": {"type": "number"},
            },
            "required": ["invoice_id", "amount"],
        }

        new_contract = {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string"},
                "amount": {"type": "number"},
                "notes": {"type": "string"},  # New optional field
            },
            "required": ["invoice_id", "amount"],
        }

        from src.core.procedures.contract_validator import ContractValidator

        validator = ContractValidator()
        result = validator.validate_compatibility(old_contract, new_contract)

        assert result.is_compatible
        assert len(result.breaking_changes) == 0
        assert "notes" in result.non_breaking_changes[0]["field"]

    def test_adding_required_field_breaks_compatibility(self):
        """Should detect when a new required field is added (breaking change)"""
        old_contract = {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string"},
                "amount": {"type": "number"},
            },
            "required": ["invoice_id", "amount"],
        }

        new_contract = {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string"},
                "amount": {"type": "number"},
                "status": {"type": "string"},
            },
            "required": ["invoice_id", "amount", "status"],  # New required field
        }

        from src.core.procedures.contract_validator import ContractValidator

        validator = ContractValidator()
        result = validator.validate_compatibility(old_contract, new_contract)

        assert not result.is_compatible
        assert "added_required_field" in result.breaking_changes[0]["type"]
        assert result.breaking_changes[0]["field"] == "status"


class TestNestedObjectCompatibility:
    """Test compatibility validation for nested objects"""

    def test_nested_field_type_change_breaks_compatibility(self):
        """Should detect type changes in nested objects"""
        old_contract = {
            "type": "object",
            "properties": {
                "invoice": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "total": {"type": "number"},
                    },
                    "required": ["id", "total"],
                }
            },
            "required": ["invoice"],
        }

        new_contract = {
            "type": "object",
            "properties": {
                "invoice": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "total": {"type": "string"},  # Changed
                    },
                    "required": ["id", "total"],
                }
            },
            "required": ["invoice"],
        }

        from src.core.procedures.contract_validator import ContractValidator

        validator = ContractValidator()
        result = validator.validate_compatibility(old_contract, new_contract)

        assert not result.is_compatible
        assert "field_type_changed" in result.breaking_changes[0]["type"]
        assert "invoice.total" in result.breaking_changes[0]["field"]

    def test_removing_nested_required_field_breaks_compatibility(self):
        """Should detect removal of required nested fields"""
        old_contract = {
            "type": "object",
            "properties": {
                "invoice": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "total": {"type": "number"},
                        "status": {"type": "string"},
                    },
                    "required": ["id", "total", "status"],
                }
            },
            "required": ["invoice"],
        }

        new_contract = {
            "type": "object",
            "properties": {
                "invoice": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "total": {"type": "number"},
                        # status removed
                    },
                    "required": ["id", "total"],
                }
            },
            "required": ["invoice"],
        }

        from src.core.procedures.contract_validator import ContractValidator

        validator = ContractValidator()
        result = validator.validate_compatibility(old_contract, new_contract)

        assert not result.is_compatible
        assert "removed_required_field" in result.breaking_changes[0]["type"]
        assert "invoice.status" in result.breaking_changes[0]["field"]


class TestArrayCompatibility:
    """Test compatibility validation for array types"""

    def test_array_item_type_change_breaks_compatibility(self):
        """Should detect when array item type changes"""
        old_contract = {
            "type": "object",
            "properties": {
                "line_items": {
                    "type": "array",
                    "items": {"type": "string"},
                }
            },
            "required": ["line_items"],
        }

        new_contract = {
            "type": "object",
            "properties": {
                "line_items": {
                    "type": "array",
                    "items": {"type": "number"},  # Changed
                }
            },
            "required": ["line_items"],
        }

        from src.core.procedures.contract_validator import ContractValidator

        validator = ContractValidator()
        result = validator.validate_compatibility(old_contract, new_contract)

        assert not result.is_compatible
        assert "array_item_type_changed" in result.breaking_changes[0]["type"]


class TestEnumCompatibility:
    """Test compatibility validation for enum constraints"""

    def test_removing_enum_value_breaks_compatibility(self):
        """Should detect when enum values are removed"""
        old_contract = {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "approved", "rejected"],
                }
            },
            "required": ["status"],
        }

        new_contract = {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "approved"],  # rejected removed
                }
            },
            "required": ["status"],
        }

        from src.core.procedures.contract_validator import ContractValidator

        validator = ContractValidator()
        result = validator.validate_compatibility(old_contract, new_contract)

        assert not result.is_compatible
        assert "enum_value_removed" in result.breaking_changes[0]["type"]
        assert "rejected" in result.breaking_changes[0]["removed_values"]

    def test_adding_enum_value_is_compatible(self):
        """Should allow adding enum values (non-breaking)"""
        old_contract = {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "approved"],
                }
            },
            "required": ["status"],
        }

        new_contract = {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "approved", "rejected"],  # Added
                }
            },
            "required": ["status"],
        }

        from src.core.procedures.contract_validator import ContractValidator

        validator = ContractValidator()
        result = validator.validate_compatibility(old_contract, new_contract)

        assert result.is_compatible
        assert len(result.breaking_changes) == 0


class TestValidationResult:
    """Test ValidationResult structure"""

    def test_validation_result_contains_change_summary(self):
        """Should provide detailed change summary"""
        old_contract = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "amount": {"type": "number"},
            },
            "required": ["id", "amount"],
        }

        new_contract = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "amount": {"type": "number"},
                "notes": {"type": "string"},
            },
            "required": ["id", "amount"],
        }

        from src.core.procedures.contract_validator import ContractValidator

        validator = ContractValidator()
        result = validator.validate_compatibility(old_contract, new_contract)

        assert hasattr(result, "is_compatible")
        assert hasattr(result, "breaking_changes")
        assert hasattr(result, "non_breaking_changes")
        assert hasattr(result, "summary")
        assert result.summary


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_handles_empty_contracts(self):
        """Should handle empty contracts gracefully"""
        old_contract = {}
        new_contract = {}

        from src.core.procedures.contract_validator import ContractValidator

        validator = ContractValidator()
        result = validator.validate_compatibility(old_contract, new_contract)

        assert result.is_compatible

    def test_handles_missing_properties(self):
        """Should handle contracts without properties field"""
        old_contract = {"type": "object"}
        new_contract = {"type": "object", "properties": {}}

        from src.core.procedures.contract_validator import ContractValidator

        validator = ContractValidator()
        result = validator.validate_compatibility(old_contract, new_contract)

        assert result.is_compatible

    def test_handles_null_contracts(self):
        """Should raise error for None contracts"""
        from src.core.procedures.contract_validator import ContractValidator

        validator = ContractValidator()

        with pytest.raises(ValueError, match="cannot be None"):
            validator.validate_compatibility(None, {})

        with pytest.raises(ValueError, match="cannot be None"):
            validator.validate_compatibility({}, None)
