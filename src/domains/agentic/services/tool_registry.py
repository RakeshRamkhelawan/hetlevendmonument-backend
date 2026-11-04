"""
Tool Registry - Central repository for agentic tools.

Provides:
- Tool lookup by name
- Tool definition loading as DTOs
- Caching for performance
- Validation of tool configurations
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agentic.models import ToolDefinition as ToolModel
from src.domains.agentic.schemas import ToolDefinition as ToolDTO

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for managing tool definitions and their implementations.
    Decouples execution from definition.
    """

    def __init__(self) -> None:
        self._cache: dict[str, ToolDTO] = {}  # name -> ToolDTO

    async def get_tool(
        self, db: AsyncSession, tool_name: str, force_refresh: bool = False
    ) -> ToolDTO | None:
        """
        Get a tool definition by name.
        """
        if not force_refresh and tool_name in self._cache:
            return self._cache[tool_name]

        stmt = select(ToolModel).where(ToolModel.name == tool_name, ToolModel.is_active.is_(True))
        result = await db.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            return None

        dto = self._map_to_dto(model)
        self._cache[dto.name] = dto
        return dto

    async def load_tools(
        self, db: AsyncSession, tool_names: list[str], force_refresh: bool = False
    ) -> list[ToolDTO]:
        """
        Load a batch of tools by name.
        """
        # Check cache first
        missing_names: list[str] = []
        loaded_tools: list[ToolDTO] = []

        if not force_refresh:
            for name in tool_names:
                if name in self._cache:
                    loaded_tools.append(self._cache[name])
                else:
                    missing_names.append(name)
        else:
            missing_names = tool_names

        if not missing_names:
            return loaded_tools

        # Load missing from DB
        stmt = select(ToolModel).where(
            ToolModel.name.in_(missing_names), ToolModel.is_active.is_(True)
        )
        result = await db.execute(stmt)
        models = result.scalars().all()

        for model in models:
            dto = self._map_to_dto(model)
            self._cache[dto.name] = dto
            loaded_tools.append(dto)

        return loaded_tools

    def _map_to_dto(self, model: ToolModel) -> ToolDTO:
        """Map SQLAlchemy model to Pydantic DTO."""
        config: dict[str, Any] = model.implementation_config or {}  # type: ignore[assignment]

        # Handle cases where config keys vary
        version = config.get("version", "1.0.0")
        module_path = config.get("module_path") or config.get("module", "")
        function_name = config.get("function_name") or config.get("func", "")

        return ToolDTO(
            id=model.id,
            name=model.name,
            description=model.description,
            version=version,
            # Execution details
            module_path=module_path,
            function_name=function_name,
            parameters_schema=model.function_schema,  # type: ignore[arg-type]  # Map DB function_schema -> DTO parameters_schema
            # Metadata
            required_permissions=model.required_permissions or [],  # type: ignore[arg-type]
            is_active=model.is_active,
        )

    def clear_cache(self) -> None:
        """Clear internal cache."""
        self._cache.clear()


# Singleton
_registry_instance: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ToolRegistry()
    return _registry_instance
