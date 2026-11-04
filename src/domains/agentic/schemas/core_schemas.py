"""
Agentic Domain Schemas - Pydantic DTOs for Clean Architecture.

These schemas decouple the Service Layer from the Database Layer (SQLAlchemy).
Services should return these objects, not database models.
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Enums
# =============================================================================


class FeatureCategory(str, Enum):
    CONTENT_CREATION = "content_creation"
    KNOWLEDGE_MGMT = "knowledge_mgmt"
    CODE_DEV = "code_dev"
    DATA_ANALYTICS = "data_analytics"
    SYSTEM_OPS = "system_ops"
    MARKETPLACE = "marketplace"
    CUSTOM = "custom"


# =============================================================================
# Feature Schemas
# =============================================================================


class FeatureDefinition(BaseModel):
    """
    DTO for a Feature, fully decoupled from DB.
    """

    id: str
    category: str  # Use str to be flexible with DB values, or FeatureCategory
    display_name: dict[str, str] = Field(default_factory=dict)
    description: dict[str, str] = Field(default_factory=dict)

    # Configuration
    domain_context: str | None = None
    route_patterns: list[str] = Field(default_factory=list)
    intent_keywords: dict[str, list[str]] = Field(default_factory=dict)

    # Relationships (IDs only)
    prompt_template_id: int | None = None
    available_tools: list[str] = Field(default_factory=list)
    required_permissions: list[str] = Field(default_factory=list)

    # Metadata
    tenant_id: int | None = None
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)

    def get_display_name(self, locale: str) -> str:
        """Get display name in user's locale with strict fallback."""
        # 1. Try exact locale (e.g., 'nl_NL')
        if locale in self.display_name:
            return self.display_name[locale]

        # 2. Try language code (e.g., 'nl')
        lang = locale.split("_")[0]
        if lang in self.display_name:
            return self.display_name[lang]

        # 3. Fallback to English
        if "en" in self.display_name:
            return self.display_name["en"]

        # 4. Fallback to ID
        return self.id

    def get_description(self, locale: str) -> str:
        """Get description in user's locale with strict fallback."""
        # 1. Try exact locale
        if locale in self.description:
            return self.description[locale]

        # 2. Try language code
        lang = locale.split("_")[0]
        if lang in self.description:
            return self.description[lang]

        # 3. Fallback to English
        if "en" in self.description:
            return self.description["en"]

        # 4. Fallback to empty string
        return ""


# =============================================================================
# Tool Schemas
# =============================================================================


class ToolDefinition(BaseModel):
    """DTO for a Tool."""

    id: int
    name: str
    description: str
    version: str

    # Execution
    module_path: str
    function_name: str
    parameters_schema: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type

    # Restrictions
    required_permissions: list[str] = Field(default_factory=list)
    compatible_features: list[str] = Field(default_factory=list)

    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


class ToolExecutionResult(BaseModel):
    """Result of a tool execution."""

    success: bool
    result: Any = None
    error: str | None = None
    execution_time_ms: float = 0.0


# =============================================================================
# Prompt Schemas
# =============================================================================


class PromptContext(BaseModel):
    """Input context for prompt composition."""

    feature_id: str
    tenant_id: int
    user_id: int
    locale: str = "en_US"
    session_id: str | None = None
    additional_context: str | None = None

    # Optional overrides
    domain_override: str | None = None


class ComposedPrompt(BaseModel):
    """The final output of the PromptComposer."""

    system_prompt: str
    tools: list[dict[str, Any]]  # LLM-ready tool definitions  # TODO(TYPE): replace Any with concrete type
    metadata: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
