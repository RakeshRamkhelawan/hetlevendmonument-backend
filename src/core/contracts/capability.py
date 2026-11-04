"""
Capability Contract Systeem

Implementeert capability-first architectuur voor workflow execution.
Zorgt dat nodes alleen uitvoerbaar zijn als ze resolven naar geldige capabilities.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import jsonschema
from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate as jsonschema_validate
from pydantic import BaseModel, Field, ValidationError, validator


# Type alias for capability identifiers (string-based keys).
CapabilityKey = str


class InputSchema(BaseModel):
    """Schema definition for capability inputs (TDD placeholder)."""

    type: str = "object"
    properties: dict = {}  # type: ignore[type-arg]
    required: list = []  # type: ignore[type-arg]


class OutputSchema(BaseModel):
    """Schema definition for capability outputs (TDD placeholder)."""

    type: str = "object"
    properties: dict = {}  # type: ignore[type-arg]


class CapabilityValidationError(Exception):
    """Base exception voor capability validatie fouten."""

    pass


class UnknownCapabilityError(CapabilityValidationError):
    """Fout: Capability key is niet geregistreerd."""

    def __init__(self, capability_key: str) -> None:
        self.capability_key = capability_key
        super().__init__(f"Unknown capability: '{capability_key}'")


class SchemaMismatchError(CapabilityValidationError):
    """Fout: Input/output schema komt niet overeen."""

    def __init__(self, field: str, detail: str) -> None:
        self.field = field
        self.detail = detail
        super().__init__(f"Schema mismatch in '{field}': {detail}")


class RetryPolicy(BaseModel):
    """Configuratie voor retry gedrag bij failures."""

    max_retries: int = Field(default=3, ge=0, le=10)
    max_attempts: int = Field(default=3, ge=1, le=10)  # alias for max_retries (TDD compatibility)
    backoff_strategy: str = Field(default="exponential", pattern="^(fixed|linear|exponential)$")
    initial_delay_ms: int = Field(default=1000, ge=100, le=60000)
    max_delay_ms: int = Field(default=30000, ge=1000, le=300000)
    retry_on: list[str] = Field(
        default_factory=lambda: ["timeout", "rate_limit", "transient_error"]
    )

    class Config:
        frozen = True


class FallbackPolicy(BaseModel):
    """Configuratie voor fallback naar alternatieve capability."""

    enabled: bool = False  # TDD compatibility field
    fallback_capability: str | None = None
    on_failure_types: list[str] = Field(default_factory=list)
    timeout_fallback_ms: int = Field(default=5000, ge=1000, le=30000)
    timeout_ms: int = Field(default=30000, ge=1000, le=300000)  # TDD compatibility alias

    class Config:
        frozen = True


class IdempotencyKeyConfig(BaseModel):
    """Configuratie voor idempotency key generatie (TDD stub)."""

    enabled: bool = False
    key_format: str = "{tenant_id}:{workflow_id}:{node_id}"

    class Config:
        frozen = True


class AuditPolicy(BaseModel):
    """Configuratie voor audit logging van capability execution."""

    log_input: bool = True
    log_output: bool = True
    log_duration: bool = True
    log_metadata: bool = True
    pii_fields: list[str] = Field(default_factory=list)
    retention_days: int = Field(default=90, ge=7, le=365)

    class Config:
        frozen = True


class CapabilityContract(BaseModel):
    """
    Contract definitie voor een capability.

    Een capability is een herbruikbare eenheid van functionaliteit die:
    - Een duidelijk input/output schema heeft
    - Retry/fallback policies definieert
    - Idempotent is (via idempotency key)
    - Auditbaar is
    """

    capability_key: str = Field(..., min_length=1, max_length=100)
    input_schema: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        ..., description="JSON Schema voor input validatie"
    )  # TODO(TYPE): replace Any with concrete type
    output_schema: dict[str, Any] = Field(
        ..., description="JSON Schema voor output validatie"
    )  # TODO(TYPE): replace Any with concrete type

    # Retry configuratie
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)

    # Fallback configuratie
    fallback_policy: FallbackPolicy = Field(default_factory=FallbackPolicy)

    # Idempotency configuratie
    idempotency_key_template: str | None = Field(
        default=None, description="Template voor idempotency key, bv: 'email:{to}:{subject}:{date}'"
    )
    idempotency_key: IdempotencyKeyConfig | None = Field(
        default=None, description="Idempotency key configuration (TDD compatibility)"
    )

    # Audit configuratie
    audit_policy: AuditPolicy = Field(default_factory=AuditPolicy)

    # Metadata
    description: str | None = Field(default=None, max_length=500)
    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    tags: list[str] = Field(default_factory=list)
    deprecated: bool = Field(default=False)

    @validator("capability_key")
    def validate_capability_key(cls, v: str) -> str:
        """Valideer capability_key formaat (alleen lowercase, underscores, cijfers)."""
        if not re.match(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$", v):
            raise ValueError(
                f"Capability key '{v}' is invalid. "
                "Must start with lowercase letter, contain only lowercase letters, "
                "numbers, underscores, and dot-separated namespaces (e.g. 'email.send')."
            )
        return v

    @validator("input_schema", "output_schema")
    def validate_schema_is_object(
        cls,
        v: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Valideer dat schema een geldig object is."""
        if not isinstance(v, dict):
            raise ValueError("Schema must be a dictionary (JSON Schema object)")

        # Basis JSON Schema validatie
        if "type" not in v:
            raise ValueError("Schema must have a 'type' field")

        return v

    def validate_input(
        self, input_data: dict[str, object]
    ) -> tuple[bool, list[str]]:
        """Validate input data against the input schema.

        Returns: (is_valid: bool, errors: list[str]) tuple.
        """
        errors: list[str] = []
        try:
            jsonschema_validate(instance=input_data, schema=self.input_schema)
        except JsonSchemaValidationError as e:
            errors.append(f"Input validation failed: {e.message}")
            if e.path:
                field = ".".join(str(p) for p in e.path)
                errors.append(f"Field '{field}' has error: {e.message}")

        return (len(errors) == 0, errors)

    def validate_output(
        self,
        output_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """
        Valideer output data tegen het output schema.

        Returns: List[Any] van foutmeldingen (leeg als validatie slaagt)  # TODO(TYPE): replace Any with concrete type
        """
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        try:
            jsonschema_validate(instance=output_data, schema=self.output_schema)
        except JsonSchemaValidationError as e:
            errors.append(f"Output validation failed: {e.message}")

        return errors

    def generate_idempotency_key(
        self,
        input_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str | None:  # TODO(TYPE): replace Any with concrete type
        """
        Genereer idempotency key op basis van template en input data.

        Args:
            input_data: De input data voor de capability execution

        Returns:
            Idempotency key of None als geen template geconfigureerd
        """
        if not self.idempotency_key_template:
            return None

        try:
            key = self.idempotency_key_template.format(
                **input_data, date=datetime.now(timezone.utc).strftime("%Y%m%d")
            )
            return key
        except KeyError as e:
            # Missing key in template, return None
            return None


@dataclass
class ValidationResult:
    """Resultaat van capability validatie."""

    is_valid: bool
    resolved_capability: CapabilityContract | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class CapabilityRegistry:
    """
    Registry voor capability contracts.

    Centrale opslag voor alle geregistreerde capabilities.
    Thread-safe (indien nodig later uit te breiden).
    """

    def __init__(self) -> None:
        self._capabilities: dict[str, CapabilityContract] = {}

    def register(self, contract: CapabilityContract, allow_overwrite: bool = False) -> None:
        """
        Registreer een capability contract.

        Args:
            contract: Het capability contract om te registreren
            allow_overwrite: Of bestaande capabilities overschreven mogen worden

        Raises:
            CapabilityValidationError: Als capability al geregistreerd is en allow_overwrite=False
        """
        key = contract.capability_key

        if key in self._capabilities and not allow_overwrite:
            raise CapabilityValidationError(
                f"Capability '{key}' is already registered. Use allow_overwrite=True to update."
            )

        self._capabilities[key] = contract

    def unregister(self, capability_key: str) -> bool:
        """
        Deregistreer een capability.

        Returns:
            True als verwijderd, False als niet gevonden
        """
        if capability_key in self._capabilities:
            del self._capabilities[capability_key]
            return True
        return False

    def resolve(self, capability_key: str) -> CapabilityContract:
        """
        Resolve een capability key naar een contract.

        Args:
            capability_key: De key om te resolven

        Returns:
            Het capability contract

        Raises:
            UnknownCapabilityError: Als capability niet gevonden
        """
        if capability_key not in self._capabilities:
            raise UnknownCapabilityError(capability_key)

        return self._capabilities[capability_key]

    def is_registered(self, capability_key: str) -> bool:
        """Check of een capability geregistreerd is."""
        return capability_key in self._capabilities

    def list_capabilities(self, tags: set[str] | None = None) -> list[str]:
        """
        Lijst alle geregistreerde capability keys.

        Args:
            tags: Optionele filter op tags (alle moeten matchen)

        Returns:
            Lijst van capability keys
        """
        if tags is None:
            return list(self._capabilities.keys())

        return [
            key for key, contract in self._capabilities.items() if tags.issubset(set(contract.tags))
        ]

    def get_all(self) -> dict[str, CapabilityContract]:
        """Get alle geregistreerde capabilities (kopie)."""
        return self._capabilities.copy()

    def clear(self) -> None:
        """Verwijder alle geregistreerde capabilities (voor tests)."""
        self._capabilities.clear()


class CapabilityResolver:
    """
    Resolver voor workflow nodes naar capabilities.

    Valideert dat nodes correct resolven naar capabilities en
    dat hun input data valide is.
    """

    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def validate_node(
        self,
        node: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> ValidationResult:  # TODO(TYPE): replace Any with concrete type
        """
        Valideer een workflow node.

        Args:
            node: Workflow node met minimaal 'capability_key' en 'input'

        Returns:
            ValidationResult met is_valid, errors, en resolved capability
        """
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        warnings: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        resolved = None

        # Check of node een capability_key heeft
        if "capability_key" not in node:
            errors.append("Node missing required field: 'capability_key'")
            return ValidationResult(is_valid=False, errors=errors)

        capability_key = node["capability_key"]

        # Probeer capability te resolven
        try:
            contract = self.registry.resolve(capability_key)
            resolved = contract
        except UnknownCapabilityError as e:
            errors.append(f"Unknown capability: '{capability_key}'")
            return ValidationResult(is_valid=False, errors=errors)

        # Check of capability deprecated is
        if contract.deprecated:
            warnings.append(f"Capability '{capability_key}' is deprecated")

        # Valideer input als aanwezig
        if "input" in node:
            input_data = node["input"]
            if not isinstance(input_data, dict):
                errors.append(f"Node 'input' must be an object, got {type(input_data).__name__}")
            else:
                _, schema_errors = contract.validate_input(input_data)
                errors.extend(schema_errors)
        else:
            warnings.append("Node has no 'input' field")

        return ValidationResult(
            is_valid=len(errors) == 0,
            resolved_capability=resolved,
            errors=errors,
            warnings=warnings,
        )

    def validate_workflow(
        self,
        workflow: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, ValidationResult]:  # TODO(TYPE): replace Any with concrete type
        """
        Valideer een volledige workflow.

        Args:
            workflow: Workflow object met 'nodes' lijst

        Returns: Dict[str, Any] mapping node_id -> ValidationResult  # TODO(TYPE): replace Any with concrete type
        """
        results: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        if "nodes" not in workflow:
            return {
                "_workflow": ValidationResult(is_valid=False, errors=["Workflow missing 'nodes'"])
            }

        for node in workflow["nodes"]:
            node_id = node.get("id", "unknown")
            results[node_id] = self.validate_node(node)

        return results


# Singleton instance voor globale registry (optioneel)
_global_registry: CapabilityRegistry | None = None


def get_global_registry() -> CapabilityRegistry:
    """Get of create globale capability registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = CapabilityRegistry()
    return _global_registry
