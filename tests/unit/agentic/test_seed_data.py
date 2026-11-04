"""
Test Seed Data Integrity - TDD Red Phase (Corrected)

These tests validate that:
1. Seed data matches the ACTUAL SQLAlchemy model fields
2. Models can be instantiated with seed data
3. No duplicate IDs/names exist
4. Cross-references are valid
"""

from typing import Any, Dict, List, Set

import pytest

from src.domains.agentic.models import Feature, PromptTemplate, ToolDefinition
from src.domains.agentic.seeds import (
    DOMAIN_CONTEXT_TEMPLATES,
    INITIAL_PROMPT_TEMPLATES,
    PLATFORM_FEATURES,
    TOOL_DEFINITIONS,
)

# =============================================================================
# Model Field Definitions (Source of Truth from models.py)
# =============================================================================

FEATURE_REQUIRED_FIELDS = {"id", "name", "description", "category"}
FEATURE_OPTIONAL_FIELDS = {
    "icon",
    "color",
    "keywords",
    "example_queries",
    "capabilities",
    "intent_keywords",
    "route_patterns",
    "domain_context",
    "prompt_template_id",
    "tenant_id",
    "is_active",
}

TOOL_REQUIRED_FIELDS = {
    "name",
    "display_name",
    "description",
    "category",
    "function_schema",
}
TOOL_OPTIONAL_FIELDS = {
    "implementation_type",
    "implementation_config",
    "required_permissions",
    "is_active",
}

TEMPLATE_REQUIRED_FIELDS = {"name", "version", "system_prompt"}
TEMPLATE_OPTIONAL_FIELDS = {
    "context_template",
    "output_format",
    "supported_locales",
    "localized_variants",
    "status",
    "tenant_id",
    "created_by",
}


# =============================================================================
# Feature Tests
# =============================================================================


class TestPlatformFeatures:
    """Validate platform features match Feature model."""

    def test_feature_count(self):
        """There should be exactly 8 platform features."""
        assert len(PLATFORM_FEATURES) == 8

    def test_feature_ids_unique(self):
        """All feature IDs must be unique."""
        ids = [f["id"] for f in PLATFORM_FEATURES]
        assert len(ids) == len(set(ids)), f"Duplicate feature IDs: {ids}"

    def test_features_have_required_fields(self):
        """Each feature must have all required model fields."""
        for feature in PLATFORM_FEATURES:
            missing = FEATURE_REQUIRED_FIELDS - set(feature.keys())
            assert not missing, f"Feature {feature.get('id')} missing required fields: {missing}"

    def test_features_have_no_unknown_fields(self):
        """Features should not have fields that don't exist in the model."""
        all_valid_fields = FEATURE_REQUIRED_FIELDS | FEATURE_OPTIONAL_FIELDS
        for feature in PLATFORM_FEATURES:
            unknown = set(feature.keys()) - all_valid_fields
            assert not unknown, f"Feature {feature.get('id')} has unknown fields: {unknown}"

    def test_features_can_instantiate_model(self):
        """Each feature seed data should successfully instantiate a Feature model."""
        for feature_data in PLATFORM_FEATURES:
            # Filter to only valid model fields
            valid_fields = FEATURE_REQUIRED_FIELDS | FEATURE_OPTIONAL_FIELDS
            model_data = {k: v for k, v in feature_data.items() if k in valid_fields}

            # This should not raise any exception
            feature = Feature(**model_data)
            assert feature.id == feature_data["id"]
            assert feature.name == feature_data["name"]
            assert feature.category == feature_data["category"]


# =============================================================================
# Tool Definition Tests
# =============================================================================


class TestToolDefinitions:
    """Validate tool definitions match ToolDefinition model."""

    def test_tool_count(self):
        """There should be exactly 15 tool definitions."""
        assert len(TOOL_DEFINITIONS) == 15

    def test_tool_names_unique(self):
        """All tool names must be unique."""
        names = [t["name"] for t in TOOL_DEFINITIONS]
        assert len(names) == len(set(names)), f"Duplicate tool names: {names}"

    def test_tools_have_required_fields(self):
        """Each tool must have all required model fields."""
        for tool in TOOL_DEFINITIONS:
            missing = TOOL_REQUIRED_FIELDS - set(tool.keys())
            assert not missing, f"Tool {tool.get('name')} missing required fields: {missing}"

    def test_tools_have_no_unknown_fields(self):
        """Tools should not have fields that don't exist in the model."""
        all_valid_fields = TOOL_REQUIRED_FIELDS | TOOL_OPTIONAL_FIELDS
        for tool in TOOL_DEFINITIONS:
            unknown = set(tool.keys()) - all_valid_fields
            assert not unknown, f"Tool {tool.get('name')} has unknown fields: {unknown}"

    def test_tools_can_instantiate_model(self):
        """Each tool seed data should successfully instantiate a ToolDefinition model."""
        for tool_data in TOOL_DEFINITIONS:
            # Filter to only valid model fields
            valid_fields = TOOL_REQUIRED_FIELDS | TOOL_OPTIONAL_FIELDS
            model_data = {k: v for k, v in tool_data.items() if k in valid_fields}

            # This should not raise any exception
            tool = ToolDefinition(**model_data)
            assert tool.name == tool_data["name"]
            assert tool.display_name == tool_data["display_name"]
            assert tool.category == tool_data["category"]

    def test_function_schema_is_valid(self):
        """Each tool's function_schema must be a valid JSON schema object."""
        for tool in TOOL_DEFINITIONS:
            schema = tool.get("function_schema", {})
            assert isinstance(schema, dict), f"Tool {tool['name']} schema not a dict"
            assert "type" in schema, f"Tool {tool['name']} schema missing 'type'"
            assert schema["type"] == "object", f"Tool {tool['name']} schema type must be 'object'"
            assert "properties" in schema, f"Tool {tool['name']} schema missing 'properties'"


# =============================================================================
# Prompt Template Tests
# =============================================================================


class TestPromptTemplates:
    """Validate prompt templates match PromptTemplate model."""

    def test_template_count(self):
        """There should be exactly 5 prompt templates."""
        assert len(INITIAL_PROMPT_TEMPLATES) == 5

    def test_template_names_unique(self):
        """All template names must be unique."""
        names = [t["name"] for t in INITIAL_PROMPT_TEMPLATES]
        assert len(names) == len(set(names)), f"Duplicate template names: {names}"

    def test_templates_have_required_fields(self):
        """Each template must have all required model fields."""
        for template in INITIAL_PROMPT_TEMPLATES:
            missing = TEMPLATE_REQUIRED_FIELDS - set(template.keys())
            assert (
                not missing
            ), f"Template {template.get('name')} missing required fields: {missing}"

    def test_templates_have_no_unknown_fields(self):
        """Templates should not have fields that don't exist in the model."""
        all_valid_fields = TEMPLATE_REQUIRED_FIELDS | TEMPLATE_OPTIONAL_FIELDS
        for template in INITIAL_PROMPT_TEMPLATES:
            unknown = set(template.keys()) - all_valid_fields
            assert not unknown, f"Template {template.get('name')} has unknown fields: {unknown}"

    def test_templates_can_instantiate_model(self):
        """Each template seed data should successfully instantiate a PromptTemplate model."""
        for template_data in INITIAL_PROMPT_TEMPLATES:
            # Filter to only valid model fields
            valid_fields = TEMPLATE_REQUIRED_FIELDS | TEMPLATE_OPTIONAL_FIELDS
            model_data = {k: v for k, v in template_data.items() if k in valid_fields}

            # This should not raise any exception
            template = PromptTemplate(**model_data)
            assert template.name == template_data["name"]
            assert template.version == template_data["version"]
            assert len(template.system_prompt) > 50

    def test_system_prompt_not_empty(self):
        """Each template must have a non-empty system_prompt."""
        for template in INITIAL_PROMPT_TEMPLATES:
            prompt = template.get("system_prompt", "")
            assert (
                len(prompt.strip()) > 50
            ), f"Template {template['name']} has empty or too short system_prompt"


# =============================================================================
# Domain Context Tests
# =============================================================================


class TestDomainContexts:
    """Validate the 6 domain context templates."""

    def test_domain_count(self):
        """There should be exactly 6 domain contexts."""
        assert len(DOMAIN_CONTEXT_TEMPLATES) == 6

    def test_expected_domain_keys(self):
        """The expected 6 domains should be present."""
        expected = {
            "healthcare",
            "finance",
            "cultural_heritage",
            "ecommerce",
            "education",
            "legal",
        }
        actual = set(DOMAIN_CONTEXT_TEMPLATES.keys())
        assert expected == actual, f"Unexpected domains. Expected {expected}, got {actual}"

    def test_domains_have_context_prompt(self):
        """Each domain must have a context_prompt."""
        for domain, data in DOMAIN_CONTEXT_TEMPLATES.items():
            assert "context_prompt" in data, f"Domain {domain} missing context_prompt"
            assert (
                len(data["context_prompt"].strip()) > 50
            ), f"Domain {domain} has empty context_prompt"

    def test_domains_have_required_structure(self):
        """Each domain must have prohibited_actions and required_disclaimers."""
        for domain, data in DOMAIN_CONTEXT_TEMPLATES.items():
            assert "prohibited_actions" in data, f"Domain {domain} missing prohibited_actions"
            assert isinstance(data["prohibited_actions"], list)
            assert "required_disclaimers" in data, f"Domain {domain} missing required_disclaimers"
            assert isinstance(data["required_disclaimers"], list)
