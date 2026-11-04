"""Pydantic models for agent configuration validation."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, validator


class AgentStatus(str, Enum):
    """Agent lifecycle status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"


class ValidationStatus(str, Enum):
    """Configuration validation status."""

    GENERATED = "generated"
    MANUAL = "manual"
    VERIFIED = "verified"


class Priority(str, Enum):
    """Agent priority level."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AgentInfo(BaseModel):
    """Agent identification information."""

    id: int = Field(..., gt=0, lt=1000, description="Unique agent ID")
    name: str = Field(..., min_length=3, max_length=100, description="Agent class name")
    version: str = Field(
        default="1.0.0",
        pattern=r"^\d+\.\d+\.\d+$",
        description="Semantic version",
    )
    status: AgentStatus = Field(default=AgentStatus.ACTIVE, description="Agent lifecycle status")
    validation_status: ValidationStatus = Field(
        default=ValidationStatus.GENERATED,
        description="Configuration validation status",
    )

    @validator("name")
    def name_must_end_with_agent(cls, v: str) -> str:
        if not v.endswith("Agent"):
            raise ValueError(f"Agent name must end with 'Agent': {v}")
        return v

    @validator("name")
    def name_must_be_pascal_case(cls, v: str) -> str:
        if not v[0].isupper():
            raise ValueError(f"Agent name must start with uppercase: {v}")
        return v


class AgentClassification(BaseModel):
    """Agent classification and categorization."""

    category: Literal["Technical", "Enterprise", "Core", "ALS", "Subagent"] = Field(
        ..., description="Primary agent category"
    )
    subcategory: str = Field(..., min_length=1, max_length=100, description="Subcategory")
    specialisation: str = Field(
        ..., min_length=5, max_length=200, description="Agent specialization"
    )
    department: str = Field(..., min_length=1, max_length=100, description="Department")
    agent_type_enum: str = Field(..., min_length=1, max_length=50, description="Agent type")


class AgentTechnical(BaseModel):
    """Technical implementation details."""

    parent_class: str = Field(..., min_length=1, max_length=50, description="Parent class name")
    technology: Literal["LLM", "ML", "Hybrid", "Vision", "Rule"] = Field(
        ..., description="Core technology"
    )
    file: str = Field(..., pattern=r".*\.py$", description="Python implementation file")
    full_path: str = Field(..., min_length=10, description="Full path to Python file")
    yaml_config_path: str = Field(..., pattern=r".*\.yaml$", description="Path to YAML config")


class AgentBehaviour(BaseModel):
    """Agent behavioral configuration."""

    learning_enabled: bool = Field(default=False, description="Whether learning is enabled")
    toolbroker_access: bool = Field(
        default=False, description="Whether ToolBroker access is enabled"
    )
    cross_agent_learning: Literal["Yes", "No", "ReadOnly"] = Field(
        default="No", description="Cross-agent learning mode"
    )
    priority: Priority = Field(default=Priority.MEDIUM, description="Agent priority")


class AgentPrompts(BaseModel):
    """System prompts and prompt metadata."""

    system_prompt: str = Field(..., min_length=50, max_length=8000, description="System prompt")
    prompt_source: str = Field(default="generated_v1", max_length=50, description="Prompt source")


class AgentMetadata(BaseModel):
    """Agent metadata and documentation."""

    docstring: str = Field(..., min_length=10, max_length=500, description="Class docstring")
    description: str = Field(..., min_length=10, max_length=300, description="Short description")
    tags: list[str] = Field(default_factory=list, description="Tags")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Last update timestamp"
    )
    validation_warnings: list[str] = Field(default_factory=list, description="Validation warnings")

    @validator("tags")
    def validate_tags(cls, v: list[str]) -> list[str]:
        if len(v) > 20:
            raise ValueError("Too many tags (max 20)")
        for tag in v:
            if len(tag) > 50:
                raise ValueError(f"Tag too long: {tag}")
        return v


class AgentDefinitionV1(BaseModel):
    """Agent Definition Standard v1.0 fields.

    Standalone model - not part of AgentConfig.
    Used by AgentFactory to expose v1.0 metadata from .md frontmatter.
    """

    role: str | None = None
    task_scope: str | None = None
    stack_layer: str | None = None
    trigger_conditions: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    tools: list[str] | None = None
    collaborates_with: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    escalation_path: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    output_format: str | None = None
    constraints: list[str] | None = None
    memory_type: str | None = None
    confidence_threshold: float | None = None
    version: str | None = None
    tags: list[str] | None = None


class AgentConfig(BaseModel):
    """Complete agent configuration model."""

    agent: AgentInfo = Field(..., description="Agent identification")
    classification: AgentClassification = Field(..., description="Classification")
    technical: AgentTechnical = Field(..., description="Technical details")
    behaviour: AgentBehaviour = Field(..., description="Behavioral config")
    prompts: AgentPrompts = Field(..., description="Prompts")
    capabilities: list[str] = Field(default_factory=list, description="Capabilities")
    skills: list[str] = Field(default_factory=list, description="Skills")
    public_methods: list[str] = Field(
        default_factory=list, description="Public methods"
    )
    metadata: AgentMetadata = Field(..., description="Metadata")

    class Config:
        validate_assignment = True
        extra = "forbid"

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for serialization."""
        return self.dict()

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "AgentConfig":
        """Load from YAML file."""
        import yaml

        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data)
