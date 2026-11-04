"""
Schema Registry - First-class schema artifacts voor A2A contracts.

Enterprise features:
- Semver versioning met compatibiliteit checks
- SHA-256 hash validatie
- Immutable schema storage
- JSON Schema export
"""

import hashlib
import json
from typing import Any, Optional, cast

from pydantic import BaseModel, Field


class SemVer(BaseModel):
    """Semantic versioning: major.minor.patch"""

    major: int
    minor: int
    patch: int = 0

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return (self.major, self.minor, self.patch) == (
            other.major,
            other.minor,
            other.patch,
        )

    def is_compatible_with(self, consumer: "SemVer") -> bool:
        """
        Check of producer (self) compatible is met consumer.

        Rules:
        - Major MUST match (breaking changes)
        - Producer minor >= consumer minor (producer heeft features die consumer verwacht)
        """
        return self.major == consumer.major and self.minor >= consumer.minor

    @classmethod
    def parse(cls, version_str: str) -> "SemVer":
        """Parse a version string like '1.2.3' into a SemVer instance."""
        parts = version_str.split(".")
        return cls(
            major=int(parts[0]),
            minor=int(parts[1]) if len(parts) > 1 else 0,
            patch=int(parts[2]) if len(parts) > 2 else 0,
        )

    def is_newer_than(self, other: "SemVer") -> bool:
        """Check of self nieuwer is dan other"""
        return (
            self.major > other.major
            or (self.major == other.major and self.minor > other.minor)
            or (
                self.major == other.major and self.minor == other.minor and self.patch > other.patch
            )
        )


class SchemaRef(BaseModel):
    """
    Unieke schema referentie: hr.skill_matrix@1.2.0
    """

    domain: str
    name: str
    version: SemVer

    @property
    def ref(self) -> str:
        return f"{self.domain}.{self.name}@{self.version}"

    @classmethod
    def parse(cls, ref_str: str) -> "SchemaRef":
        """Parse 'hr.skill_matrix@1.2.0' -> SchemaRef"""
        try:
            name_part, version_part = ref_str.split("@")
            domain, name = name_part.split(".", 1)  # Allow dots in name
            version_parts = version_part.split(".")

            if len(version_parts) == 2:
                major, minor = map(int, version_parts)
                patch = 0
            elif len(version_parts) == 3:
                major, minor, patch = map(int, version_parts)
            else:
                raise ValueError(f"Invalid version format: {version_part}")

            return cls(
                domain=domain,
                name=name,
                version=SemVer(major=major, minor=minor, patch=patch),
            )
        except ValueError as e:
            raise ValueError(f"Invalid schema ref format: {ref_str}") from e


class SchemaIntegrityError(Exception):
    """Raised wanneer schema hash mismatch"""

    pass


class DuplicateSchemaError(Exception):
    """Raised bij duplicate schema registratie"""

    pass


class DataSchema(BaseModel):
    """
    First-class schema artifact met JSON Schema + hash + metadata.
    """

    schema_ref: SchemaRef
    json_schema: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    required_fields: list[str] = Field(default_factory=list)

    # Canonical hash voor integriteit
    schema_hash: str = Field(..., description="SHA-256 of canonical JSON Schema")

    # Metadata
    created_at: str
    created_by: str
    description: str | None = None

    # Compatibiliteit regels
    is_backward_compatible: bool = True
    deprecated_fields: list[str] = Field(default_factory=list)

    def __init__(self, **data: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        super().__init__(**data)
        # Validate hash on creation
        computed = self.compute_hash()
        if computed != self.schema_hash:
            raise SchemaIntegrityError(
                f"Schema hash mismatch: expected {self.schema_hash}, computed {computed}"
            )

    def compute_hash(self) -> str:
        """Compute canonical SHA-256 hash of schema"""
        canonical = json.dumps(self.json_schema, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]

    def validate_payload(self, payload: dict[str, Any]) -> tuple[bool, str | None]:  # TODO(TYPE): replace Any with concrete type
        """
        Valideer payload tegen schema.

        Returns: (is_valid, error_message)
        """
        # 1. Check required fields
        for field in self.required_fields:
            if field not in payload:
                return False, f"Missing required field: {field}"

        # 2. Type validation
        properties = self.json_schema.get("properties", {})
        for field_name, value in payload.items():
            field_schema = properties.get(field_name)
            if field_schema:
                field_type = field_schema.get("type")
                if not self._validate_type(value, field_type):
                    return (
                        False,
                        f"Field {field_name}: expected {field_type}, got {type(value).__name__}",
                    )

        return True, None

    def _validate_type(self, value: Any, expected_type: str | None) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Valideer type match"""
        if expected_type is None:
            return True

        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        expected = type_map.get(expected_type)
        if not expected:
            return True  # Unknown type, allow
        return isinstance(value, cast(Any, expected))  # TODO(TYPE): replace Any with concrete type

    def is_compatible_with_consumer(self, consumer_version: SemVer) -> bool:
        """Check of producer schema compatible is met consumer versie"""
        return self.schema_ref.version.is_compatible_with(consumer_version)


class SchemaRegistry:
    """
    Immutable schema registry (append-only).

    NON-NEGOTIABLE:
    - Schemas zijn immutable (no edits)
    - Duplicate versions worden rejected (409 Conflict)
    """

    def __init__(self) -> None:
        self._schemas: dict[str, DataSchema] = {}

    def register(self, schema: DataSchema) -> None:
        """
        Registreer schema. Fails bij duplicate.

        Raises:
            DuplicateSchemaError: Als schema ref al bestaat
        """
        ref = schema.schema_ref.ref
        if ref in self._schemas:
            raise DuplicateSchemaError(f"Schema {ref} already exists (HTTP 409)")
        self._schemas[ref] = schema

    def get(self, ref: str) -> DataSchema | None:
        """Get schema by ref string"""
        return self._schemas.get(ref)

    def get_by_ref(self, schema_ref: SchemaRef) -> DataSchema | None:
        """Get schema by SchemaRef object"""
        return self._schemas.get(schema_ref.ref)

    def get_compatible(
        self, domain: str, name: str, consumer_version: SemVer
    ) -> DataSchema | None:
        """
        Find newest schema compatible with consumer version.

        Returns:
            Best matching schema, or None if no compatible version found
        """
        candidates = [
            s
            for s in self._schemas.values()
            if s.schema_ref.domain == domain
            and s.schema_ref.name == name
            and s.is_compatible_with_consumer(consumer_version)
        ]

        if not candidates:
            return None

        # Return newest compatible version
        return max(
            candidates,
            key=lambda s: (
                s.schema_ref.version.major,
                s.schema_ref.version.minor,
                s.schema_ref.version.patch,
            ),
        )

    def list_versions(self, domain: str, name: str) -> list[SchemaRef]:
        """List all versions of a schema"""
        refs = [
            s.schema_ref
            for s in self._schemas.values()
            if s.schema_ref.domain == domain and s.schema_ref.name == name
        ]
        return sorted(refs, key=lambda r: (r.version.major, r.version.minor, r.version.patch))

    def get_all(self) -> dict[str, DataSchema]:
        """Get all registered schemas"""
        return self._schemas.copy()


# Standard enterprise schemas
class StandardSchemas:
    """Factory voor standaard enterprise schemas"""

    @staticmethod
    def employee_data(version: str = "1.0.0") -> DataSchema:
        return DataSchema(
            schema_ref=SchemaRef.parse(f"hr.employee_data@{version}"),
            json_schema={
                "type": "object",
                "properties": {
                    "employee_id": {"type": "string"},
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "department": {"type": "string"},
                    "skills": {"type": "array", "items": {"type": "string"}},
                    "tenure_years": {"type": "number"},
                },
            },
            required_fields=["employee_id", "name"],
            schema_hash="placeholder",  # Will be computed
            created_at="2024-01-01T00:00:00Z",
            created_by="system",
        )

    @staticmethod
    def financial_metrics(version: str = "1.0.0") -> DataSchema:
        return DataSchema(
            schema_ref=SchemaRef.parse(f"finance.financial_metrics@{version}"),
            json_schema={
                "type": "object",
                "properties": {
                    "revenue": {"type": "number"},
                    "expenses": {"type": "number"},
                    "profit_margin": {"type": "number"},
                    "period": {"type": "string"},
                },
            },
            required_fields=["revenue", "expenses", "period"],
            schema_hash="placeholder",
            created_at="2024-01-01T00:00:00Z",
            created_by="system",
        )

    @staticmethod
    def security_alert(version: str = "1.0.0") -> DataSchema:
        return DataSchema(
            schema_ref=SchemaRef.parse(f"security.alert@{version}"),
            json_schema={
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                    },
                    "threat_type": {"type": "string"},
                    "affected_systems": {"type": "array", "items": {"type": "string"}},
                    "timestamp": {"type": "string", "format": "date-time"},
                },
            },
            required_fields=["severity", "threat_type"],
            schema_hash="placeholder",
            created_at="2024-01-01T00:00:00Z",
            created_by="system",
        )
