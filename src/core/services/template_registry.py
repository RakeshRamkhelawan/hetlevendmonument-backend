"""
Template Registry Service
Manages workflow templates with parameter substitution and instantiation capabilities.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Optional, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions.exceptions import SanskritiError, ValidationError
from src.core.workflow.models import C7WorkflowTemplate as WorkflowTemplate


@dataclass
class WorkflowTemplateData:
    """Data class representing a workflow template"""

    template_id: str
    name: str
    category: str
    description: str
    spec: dict[str, object]  # TODO(TYPE): replace Any with concrete type
    required_integrations: list[str] | None = None
    author: str | None = None
    is_public: bool = False


class TemplateRegistry:
    """
    Singleton registry for managing workflow templates.

    Features:
    - Load templates from database
    - Get template by ID
    - List templates with category filtering
    - Instantiate templates with parameter substitution
    - Parameter substitution with {{param}} syntax
    """

    _instance: Optional["TemplateRegistry"] = None
    _templates: dict[str, WorkflowTemplateData] = {}

    def __new__(cls) -> "TemplateRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self, session: AsyncSession) -> None:
        """
        Load all templates from database into memory.

        Args:
            session: Database session for querying templates
        """
        try:
            stmt = select(WorkflowTemplate)
            result = await session.execute(stmt)
            db_templates = result.scalars().all()

            self._templates.clear()
            for template in db_templates:
                template_data = WorkflowTemplateData(
                    template_id=template.template_id,
                    name=template.name,
                    category=template.category or "general",
                    description=template.description or "",
                    spec=template.spec_json or {},
                    required_integrations=None,  # Could be extracted from spec
                    author=template.author,
                    is_public=template.is_public,
                )
                self._templates[template.template_id] = template_data

        except Exception as e:
            raise SanskritiError(
                f"Failed to initialize template registry: {str(e)}",
                error_code="TEMPLATE_REGISTRY_INIT_FAILED",
                status_code=500,
            )

    def get_template(self, template_id: str) -> WorkflowTemplateData | None:
        """
        Get template by ID.

        Args:
            template_id: Template identifier

        Returns:
            WorkflowTemplateData if found, None otherwise
        """
        return self._templates.get(template_id)

    def list_templates(self, category: str | None = None) -> list[WorkflowTemplateData]:
        """
        List all templates, optionally filtered by category.

        Args:
            category: Optional category filter

        Returns: list[WorkflowTemplateData] of WorkflowTemplateData objects
        """
        templates = list(self._templates.values())
        if category:
            templates = [t for t in templates if t.category == category]
        return templates

    def instantiate(self, template_id: str, parameters: dict[str, object]) -> dict[str, object]:
        """
        Create workflow spec from template with parameter substitution.

        Args:
            template_id: Template identifier
            parameters: Parameters for substitution

        Returns:
            Workflow specification dictionary

        Raises:
            ValueError: If template not found
            ValidationError: If parameter substitution fails
        """
        template = self.get_template(template_id)
        if not template:
            raise ValueError(f"Template '{template_id}' not found")

        try:
            # Deep copy template spec
            workflow_spec = json.loads(json.dumps(template.spec))

            # Perform parameter substitution
            self._substitute_parameters(workflow_spec, parameters)

            return cast(
                dict[str, object], workflow_spec
            )  # TODO(TYPE): replace Any with concrete type
        except Exception as e:
            raise ValidationError(
                "TEMPLATE_INSTANTIATION_FAILED",
                f"Failed to instantiate template '{template_id}': {str(e)}",
            )

    def _substitute_parameters(
        self, obj: object, parameters: dict[str, object]
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """
        Recursively substitute {{param}} placeholders in object.

        Supports:
        - Simple parameters: {{param_name}}
        - Nested parameters: {{nested.param}}

        Args:
            obj: Object to process (dict, list, or value)
            parameters: Parameter dictionary
        """
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str):
                    obj[key] = self._process_string_parameter(value, parameters)
                elif isinstance(value, (dict, list)):
                    self._substitute_parameters(value, parameters)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, str):
                    obj[i] = self._process_string_parameter(item, parameters)
                elif isinstance(item, (dict, list)):
                    self._substitute_parameters(item, parameters)

    def _process_string_parameter(
        self, value: str, parameters: dict[str, object]
    ) -> object:  # TODO(TYPE): replace Any with concrete type
        """
        Process string parameter substitution.

        Args:
            value: String value that may contain parameters
            parameters: Parameter dictionary

        Returns:
            Substituted value or original value if no substitution needed
        """
        # Handle simple parameter: {{param_name}}
        if value.startswith("{{") and value.endswith("}}"):
            param_name = value[2:-2].strip()
            if param_name in parameters:
                return parameters[param_name]
            # Try nested parameter access
            return self._get_nested_parameter(param_name, parameters)

        # Handle embedded parameters: text {{param}} more text
        pattern = r"\{\{([^}]+)\}\}"
        matches = re.findall(pattern, value)

        if matches:
            result = value
            for match in matches:
                param_name = match.strip()
                if param_name in parameters:
                    param_value = parameters[param_name]
                    result = result.replace(f"{{{{{param_name}}}}}", str(param_value))
                else:
                    # Try nested parameter access
                    nested_value = self._get_nested_parameter(param_name, parameters)
                    if nested_value is not None:
                        result = result.replace(f"{{{{{param_name}}}}}", str(nested_value))

            return result

        return value

    def _get_nested_parameter(
        self, param_path: str, parameters: dict[str, object]
    ) -> object:  # TODO(TYPE): replace Any with concrete type
        """
        Get nested parameter value using dot notation.

        Args:
            param_path: Dot-separated parameter path (e.g., "user.name")
            parameters: Parameter dictionary

        Returns:
            Parameter value or None if not found
        """
        keys = param_path.split(".")
        current = parameters

        try:
            for key in keys:
                if isinstance(current, dict) and key in current:
                    current = current[key]  # type: ignore[assignment]
                else:
                    return None
            return current
        except (TypeError, KeyError):
            return None


# Global instance accessor
def get_template_registry() -> TemplateRegistry:
    """Get the global template registry instance."""
    return TemplateRegistry()
