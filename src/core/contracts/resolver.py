"""
Capability Resolver for PRD v3.3 Phase 0.

Resolves workflow nodes to capability contracts at runtime.
Enforces contract validation before execution.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, cast

from .capability import CapabilityContract


@dataclass
class ResolutionResult:
    """
    Result of capability resolution.

    Attributes:
        success: Whether resolution succeeded
        contract: The resolved contract (if success=True)
        errors: List[Any] of error messages (if success=False)  # TODO(TYPE): replace Any with concrete type
        validation_errors: Detailed validation errors for input data
        _used_fallback: Whether a fallback capability was used
        _fallback_from: Original capability key if fallback was used
    """

    success: bool
    contract: CapabilityContract | None = None
    errors: list[str] | None = None
    validation_errors: list[str] | None = None
    _used_fallback: bool = False
    _fallback_from: str | None = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []
        if self.validation_errors is None:
            self.validation_errors = []


class CapabilityResolver:
    """
    Resolves capability keys to contracts at runtime.

    The resolver is the gatekeeper that ensures:
    1. Only registered capabilities can be executed
    2. Input data matches the contract schema
    3. Fallback capabilities are tracked

    Usage:
        registry = {
            "email.send": CapabilityContract(...),
            "sms.send": CapabilityContract(...),
        }
        resolver = CapabilityResolver(registry)

        result = resolver.resolve({
            "capability_key": "email.send",
            "inputs": {"to": "test@example.com"}
        })

        if result.success:
            execute_capability(result.contract)
        else:
            handle_error(result.errors)
    """

    def __init__(self, registry: dict[str, CapabilityContract] | None = None) -> None:
        """
        Initialize resolver with capability registry.

        Args:
            registry: Mapping[str, Any] of capability_key -> CapabilityContract  # TODO(TYPE): replace Any with concrete type
        """
        self._registry = registry or {}
        self._resolution_count = 0
        self._resolution_failures = 0

    def register(self, contract: CapabilityContract) -> None:
        """Register a new capability contract"""
        self._registry[contract.capability_key] = contract

    def unregister(self, capability_key: str) -> bool:
        """Unregister a capability. Returns True if existed."""
        if capability_key in self._registry:
            del self._registry[capability_key]
            return True
        return False

    def get_contract(self, capability_key: str) -> CapabilityContract | None:
        """Get contract by key without validation"""
        return self._registry.get(capability_key)

    def list_capabilities(self) -> list[str]:
        """List all registered capability keys"""
        return list(self._registry.keys())

    def resolve(
        self,
        node_config: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        tenant_id: str | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> ResolutionResult:
        """
        Resolve a workflow node to a capability contract.

        This is the main entry point for contract resolution.
        It validates that:
        1. The capability_key exists in the registry
        2. The input data matches the contract's input_schema

        Args:
            node_config: Workflow node configuration containing:
                - capability_key: The capability to resolve
                - inputs: Input data for the capability
            tenant_id: Optional tenant ID for logging/tracking

        Returns:
            ResolutionResult with success status and contract or errors
        """
        self._resolution_count += 1

        # Extract configuration
        capability_key = node_config.get("capability_key")
        inputs = node_config.get("inputs", {})

        # Validate capability_key exists
        if not capability_key:
            self._resolution_failures += 1
            return ResolutionResult(
                success=False, errors=["Missing required field: 'capability_key'"]
            )

        # Look up contract in registry
        contract = self._registry.get(capability_key)
        if not contract:
            self._resolution_failures += 1
            available = ", ".join(self.list_capabilities()[:5])
            if len(self.list_capabilities()) > 5:
                available += f", ... and {len(self.list_capabilities()) - 5} more"

            return ResolutionResult(
                success=False,
                errors=[
                    f"Unknown capability_key: '{capability_key}'",
                    f"Available capabilities: {available if available else 'none registered'}",
                ],
            )

        # Validate input against contract schema
        is_valid, validation_errors = contract.validate_input(inputs)
        if not is_valid:
            self._resolution_failures += 1
            return ResolutionResult(
                success=False,
                contract=contract,  # Include contract for context
                errors=[
                    f"Input validation failed for capability '{capability_key}'",
                    *validation_errors,
                ],
                validation_errors=validation_errors,
            )

        # Success!
        return ResolutionResult(success=True, contract=contract, errors=[])

    def resolve_with_fallback(
        self,
        node_config: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        tenant_id: str | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> ResolutionResult:
        """
        Resolve with automatic fallback to backup capability.

        If the primary capability resolution fails but the capability
        has a fallback configured, this method will attempt to resolve
        the fallback capability.

        Args:
            node_config: Workflow node configuration
            tenant_id: Optional tenant ID

        Returns:
            ResolutionResult (may be from fallback capability)
        """
        primary_result = self.resolve(node_config, tenant_id)

        if primary_result.success:
            return primary_result

        # Check if we have a contract with fallback
        capability_key = node_config.get("capability_key")
        if not isinstance(capability_key, str):
            return primary_result
        contract = self._registry.get(capability_key)

        if contract and contract.fallback_policy:
            fallback_key = contract.fallback_policy.fallback_capability
            if fallback_key:
                # Create fallback node config
                fallback_config = {
                    **node_config,
                    "capability_key": fallback_key,
                    "_fallback_from": capability_key,  # Track lineage
                }

                fallback_result = self.resolve(fallback_config, tenant_id)
                if fallback_result.success:
                    # Mark as fallback usage
                    return ResolutionResult(
                        success=True,
                        contract=fallback_result.contract,
                        errors=[],
                        validation_errors=[],
                        _used_fallback=True,
                        _fallback_from=capability_key,
                    )

        # Return original failure if fallback also failed or not configured
        return primary_result

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get resolution statistics"""
        return {
            "total_resolutions": self._resolution_count,
            "failed_resolutions": self._resolution_failures,
            "success_rate": (
                (self._resolution_count - self._resolution_failures) / self._resolution_count * 100
                if self._resolution_count > 0
                else 0
            ),
            "registered_capabilities": len(self._registry),
        }

    def clear_stats(self) -> None:
        """Reset resolution counters"""
        self._resolution_count = 0
        self._resolution_failures = 0
