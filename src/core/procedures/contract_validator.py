"""
Slice 2: Contract Validator - GREEN Phase Implementation

Validates backward compatibility of domain pack output contracts.
Prevents breaking changes that would affect downstream consumers.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ValidationResult:
    """Result of contract compatibility validation"""

    is_compatible: bool
    breaking_changes: list[dict[str, Any]] = field(default_factory=list)  # TODO(TYPE): replace Any with concrete type
    non_breaking_changes: list[dict[str, Any]] = field(default_factory=list)  # TODO(TYPE): replace Any with concrete type
    summary: str = ""


class ContractValidator:
    """
    Validates backward compatibility between old and new contract versions.

    Uses JSON Schema semantics to detect breaking changes like:
    - Removing required fields
    - Changing field types
    - Removing enum values
    - Changing array item types
    """

    def validate_compatibility(
        self,
        old_contract: dict[str, Any] | None,  # TODO(TYPE): replace Any with concrete type
        new_contract: dict[str, Any] | None,  # TODO(TYPE): replace Any with concrete type
    ) -> ValidationResult:
        """
        Validate that new_contract is backward compatible with old_contract.

        Args:
            old_contract: Previous version of the contract (JSON Schema format)
            new_contract: New version of the contract (JSON Schema format)

        Returns:
            ValidationResult with details of breaking/non-breaking changes

        Raises:
            ValueError: If either contract is None
        """
        if old_contract is None or new_contract is None:
            raise ValueError("Contracts cannot be None")

        # Handle empty contracts
        if not old_contract and not new_contract:
            return ValidationResult(is_compatible=True, summary="Both contracts empty")

        breaking_changes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        non_breaking_changes: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Validate properties
        old_props = old_contract.get("properties", {})
        new_props = new_contract.get("properties", {})
        old_required = set(old_contract.get("required", []))
        new_required = set(new_contract.get("required", []))

        # Check for removed fields
        for field_name in old_props:
            if field_name not in new_props:
                if field_name in old_required:
                    breaking_changes.append(
                        {
                            "type": "removed_required_field",
                            "field": field_name,
                            "message": f"Required field '{field_name}' was removed",
                        }
                    )

        # Check for type changes
        for field_name in old_props:
            if field_name in new_props:
                old_type = old_props[field_name].get("type")
                new_type = new_props[field_name].get("type")

                if old_type and new_type and old_type != new_type:
                    breaking_changes.append(
                        {
                            "type": "field_type_changed",
                            "field": field_name,
                            "old_type": old_type,
                            "new_type": new_type,
                            "message": f"Field '{field_name}' type changed from {old_type} to {new_type}",
                        }
                    )

                # Check nested objects
                if old_type == "object" and new_type == "object":
                    nested_result = self._validate_nested_object(
                        field_name,
                        old_props[field_name],
                        new_props[field_name],
                    )
                    breaking_changes.extend(nested_result["breaking"])
                    non_breaking_changes.extend(nested_result["non_breaking"])

                # Check arrays
                if old_type == "array" and new_type == "array":
                    array_result = self._validate_array(
                        field_name,
                        old_props[field_name],
                        new_props[field_name],
                    )
                    breaking_changes.extend(array_result["breaking"])
                    non_breaking_changes.extend(array_result["non_breaking"])

                # Check enums
                if "enum" in old_props[field_name]:
                    enum_result = self._validate_enum(
                        field_name,
                        old_props[field_name],
                        new_props[field_name],
                    )
                    breaking_changes.extend(enum_result["breaking"])
                    non_breaking_changes.extend(enum_result["non_breaking"])

        # Check for new required fields
        newly_required = new_required - old_required
        for field_name in newly_required:
            if field_name in new_props:
                breaking_changes.append(
                    {
                        "type": "added_required_field",
                        "field": field_name,
                        "message": f"New required field '{field_name}' was added",
                    }
                )

        # Check for new optional fields
        for field_name in new_props:
            if field_name not in old_props and field_name not in new_required:
                non_breaking_changes.append(
                    {
                        "type": "added_optional_field",
                        "field": field_name,
                        "message": f"New optional field '{field_name}' was added",
                    }
                )

        # Build summary
        is_compatible = len(breaking_changes) == 0
        summary = self._build_summary(breaking_changes, non_breaking_changes, is_compatible)

        return ValidationResult(
            is_compatible=is_compatible,
            breaking_changes=breaking_changes,
            non_breaking_changes=non_breaking_changes,
            summary=summary,
        )

    def _validate_nested_object(
        self,
        parent_field: str,
        old_schema: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        new_schema: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, list[dict[str, Any]]]:  # TODO(TYPE): replace Any with concrete type
        """Validate nested object compatibility"""
        breaking: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        non_breaking: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

        old_props = old_schema.get("properties", {})
        new_props = new_schema.get("properties", {})
        old_required = set(old_schema.get("required", []))
        new_required = set(new_schema.get("required", []))

        # Check for removed required fields
        for field_name in old_props:
            if field_name not in new_props and field_name in old_required:
                breaking.append(
                    {
                        "type": "removed_required_field",
                        "field": f"{parent_field}.{field_name}",
                        "message": f"Required nested field '{parent_field}.{field_name}' was removed",
                    }
                )

        # Check for type changes in nested fields
        for field_name in old_props:
            if field_name in new_props:
                old_type = old_props[field_name].get("type")
                new_type = new_props[field_name].get("type")

                if old_type and new_type and old_type != new_type:
                    breaking.append(
                        {
                            "type": "field_type_changed",
                            "field": f"{parent_field}.{field_name}",
                            "old_type": old_type,
                            "new_type": new_type,
                            "message": f"Nested field '{parent_field}.{field_name}' type changed",
                        }
                    )

        return {"breaking": breaking, "non_breaking": non_breaking}

    def _validate_array(
        self,
        field_name: str,
        old_schema: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        new_schema: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, list[dict[str, Any]]]:  # TODO(TYPE): replace Any with concrete type
        """Validate array compatibility"""
        breaking: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        non_breaking: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

        old_items = old_schema.get("items", {})
        new_items = new_schema.get("items", {})

        if old_items and new_items:
            old_item_type = old_items.get("type")
            new_item_type = new_items.get("type")

            if old_item_type and new_item_type and old_item_type != new_item_type:
                breaking.append(
                    {
                        "type": "array_item_type_changed",
                        "field": field_name,
                        "old_type": old_item_type,
                        "new_type": new_item_type,
                        "message": f"Array '{field_name}' item type changed from {old_item_type} to {new_item_type}",
                    }
                )

        return {"breaking": breaking, "non_breaking": non_breaking}

    def _validate_enum(
        self,
        field_name: str,
        old_schema: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        new_schema: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, list[dict[str, Any]]]:  # TODO(TYPE): replace Any with concrete type
        """Validate enum compatibility"""
        breaking: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        non_breaking: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        old_enum = set(old_schema.get("enum", []))
        new_enum = set(new_schema.get("enum", []))

        # Check for removed enum values
        removed_values = old_enum - new_enum
        if removed_values:
            breaking.append(
                {
                    "type": "enum_value_removed",
                    "field": field_name,
                    "removed_values": list(removed_values),
                    "message": f"Enum values {removed_values} were removed from '{field_name}'",
                }
            )

        # Check for added enum values (non-breaking)
        added_values = new_enum - old_enum
        if added_values:
            non_breaking.append(
                {
                    "type": "enum_value_added",
                    "field": field_name,
                    "added_values": list(added_values),
                    "message": f"Enum values {added_values} were added to '{field_name}'",
                }
            )

        return {"breaking": breaking, "non_breaking": non_breaking}

    def _build_summary(
        self,
        breaking_changes: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        non_breaking_changes: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        is_compatible: bool,
    ) -> str:
        """Build human-readable summary"""
        if is_compatible:
            if len(non_breaking_changes) == 0:
                return "No changes detected"
            else:
                return f"Compatible ({len(non_breaking_changes)} non-breaking changes)"
        else:
            return f"INCOMPATIBLE ({len(breaking_changes)} breaking changes, {len(non_breaking_changes)} non-breaking changes)"
