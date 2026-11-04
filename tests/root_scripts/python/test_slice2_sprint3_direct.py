"""
Sprint 3 Slice 2 Direct Tests: Contract Validator
Quick standalone validation (5-10 second feedback loop)
"""

from src.core.procedures.contract_validator import ContractValidator


def test_detects_breaking_change_removed_required_field():
    """Should detect when required field is removed"""
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
        },
        "required": ["invoice_id", "amount"],
    }

    validator = ContractValidator()
    result = validator.validate_compatibility(old_contract, new_contract)

    assert not result.is_compatible
    assert "removed_required_field" in result.breaking_changes[0]["type"]
    assert result.breaking_changes[0]["field"] == "status"
    print("✓ Detects removed required field")


def test_detects_breaking_change_field_type_changed():
    """Should detect when field type changes"""
    old_contract = {
        "type": "object",
        "properties": {
            "amount": {"type": "number"},
        },
        "required": ["amount"],
    }

    new_contract = {
        "type": "object",
        "properties": {
            "amount": {"type": "string"},
        },
        "required": ["amount"],
    }

    validator = ContractValidator()
    result = validator.validate_compatibility(old_contract, new_contract)

    assert not result.is_compatible
    assert "field_type_changed" in result.breaking_changes[0]["type"]
    assert result.breaking_changes[0]["old_type"] == "number"
    assert result.breaking_changes[0]["new_type"] == "string"
    print("✓ Detects field type change")


def test_allows_non_breaking_change_optional_field():
    """Should allow adding optional fields"""
    old_contract = {
        "type": "object",
        "properties": {
            "invoice_id": {"type": "string"},
        },
        "required": ["invoice_id"],
    }

    new_contract = {
        "type": "object",
        "properties": {
            "invoice_id": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["invoice_id"],
    }

    validator = ContractValidator()
    result = validator.validate_compatibility(old_contract, new_contract)

    assert result.is_compatible
    assert len(result.breaking_changes) == 0
    print("✓ Allows adding optional fields")


def test_detects_breaking_change_new_required_field():
    """Should detect when new required field is added"""
    old_contract = {
        "type": "object",
        "properties": {
            "invoice_id": {"type": "string"},
        },
        "required": ["invoice_id"],
    }

    new_contract = {
        "type": "object",
        "properties": {
            "invoice_id": {"type": "string"},
            "status": {"type": "string"},
        },
        "required": ["invoice_id", "status"],
    }

    validator = ContractValidator()
    result = validator.validate_compatibility(old_contract, new_contract)

    assert not result.is_compatible
    assert "added_required_field" in result.breaking_changes[0]["type"]
    print("✓ Detects new required field")


def test_detects_breaking_change_enum_value_removed():
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
                "enum": ["pending", "approved"],
            }
        },
        "required": ["status"],
    }

    validator = ContractValidator()
    result = validator.validate_compatibility(old_contract, new_contract)

    assert not result.is_compatible
    assert "enum_value_removed" in result.breaking_changes[0]["type"]
    assert "rejected" in result.breaking_changes[0]["removed_values"]
    print("✓ Detects removed enum values")


def test_handles_empty_contracts():
    """Should handle empty contracts gracefully"""
    validator = ContractValidator()
    result = validator.validate_compatibility({}, {})

    assert result.is_compatible
    print("✓ Handles empty contracts")


def test_raises_on_none_contracts():
    """Should raise error for None contracts"""
    validator = ContractValidator()

    try:
        validator.validate_compatibility(None, {})
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "cannot be None" in str(e)
        print("✓ Raises error for None contracts")


def main():
    """Run all direct tests"""
    print("\nSprint 3 Slice 2: Contract Validator - Direct Tests")
    print("=" * 60)

    tests = [
        test_detects_breaking_change_removed_required_field,
        test_detects_breaking_change_field_type_changed,
        test_allows_non_breaking_change_optional_field,
        test_detects_breaking_change_new_required_field,
        test_detects_breaking_change_enum_value_removed,
        test_handles_empty_contracts,
        test_raises_on_none_contracts,
    ]

    passed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__} failed: {e}")
        except Exception as e:
            print(f"✗ {test.__name__} error: {e}")

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{len(tests)} tests passed")

    if passed == len(tests):
        print("✅ All direct tests passing!")
        return 0
    else:
        print(f"❌ {len(tests) - passed} tests failed")
        return 1


if __name__ == "__main__":
    exit(main())
