"""Repository interface for Strategy Engine persistence."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from src.core.strategy.types import StrategicInsight, StrategicObjective


class StrategyRepository(ABC):
    """Abstract repository for strategy persistence."""

    @abstractmethod
    async def save_strategy(self, tenant_id: int, strategy: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Save a strategy."""
        pass

    @abstractmethod
    async def get_strategies(self, tenant_id: int) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get all strategies for a tenant."""
        pass

    @abstractmethod
    async def get_strategy(self, tenant_id: int, strategy_id: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get a specific strategy."""
        pass

    @abstractmethod
    async def delete_strategy(self, tenant_id: int, strategy_id: str) -> None:
        """Delete a strategy."""
        pass

    @abstractmethod
    async def save_objective(self, tenant_id: int, objective: StrategicObjective) -> None:
        """Save a strategic objective."""
        pass

    @abstractmethod
    async def get_active_objectives(self, tenant_id: int) -> list[StrategicObjective]:
        """Get active objectives for a tenant."""
        pass

    @abstractmethod
    async def delete_objective(self, tenant_id: int, objective_id: str) -> None:
        """Delete an objective."""
        pass

    @abstractmethod
    async def save_insight(self, tenant_id: int, insight: StrategicInsight) -> None:
        """Save a strategic insight."""
        pass

    @abstractmethod
    async def get_insights(self, tenant_id: int) -> list[StrategicInsight]:
        """Get all insights for a tenant."""
        pass

    @abstractmethod
    async def delete_insight(self, tenant_id: int, insight_id: str) -> None:
        """Delete an insight."""
        pass


class InMemoryStrategyRepository(StrategyRepository):
    """In-memory implementation for testing."""

    def __init__(self) -> None:
        self._strategies: dict[int, dict[str, dict[str, Any]]] = {}  # TODO(TYPE): replace Any with concrete type
        self._objectives: dict[int, dict[str, StrategicObjective]] = {}
        self._insights: dict[int, dict[str, StrategicInsight]] = {}

    async def save_strategy(self, tenant_id: int, strategy: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        if tenant_id not in self._strategies:
            self._strategies[tenant_id] = {}
        self._strategies[tenant_id][strategy["id"]] = strategy

    async def get_strategies(self, tenant_id: int) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        return list(self._strategies.get(tenant_id, {}).values())

    async def get_strategy(self, tenant_id: int, strategy_id: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        return self._strategies.get(tenant_id, {}).get(strategy_id)

    async def delete_strategy(self, tenant_id: int, strategy_id: str) -> None:
        if tenant_id in self._strategies:
            self._strategies[tenant_id].pop(strategy_id, None)

    async def save_objective(self, tenant_id: int, objective: StrategicObjective) -> None:
        if tenant_id not in self._objectives:
            self._objectives[tenant_id] = {}
        self._objectives[tenant_id][objective.id] = objective

    async def get_active_objectives(self, tenant_id: int) -> list[StrategicObjective]:
        return list(self._objectives.get(tenant_id, {}).values())

    async def delete_objective(self, tenant_id: int, objective_id: str) -> None:
        if tenant_id in self._objectives:
            self._objectives[tenant_id].pop(objective_id, None)

    async def save_insight(self, tenant_id: int, insight: StrategicInsight) -> None:
        if tenant_id not in self._insights:
            self._insights[tenant_id] = {}
        self._insights[tenant_id][insight.id] = insight

    async def get_insights(self, tenant_id: int) -> list[StrategicInsight]:
        return list(self._insights.get(tenant_id, {}).values())

    async def delete_insight(self, tenant_id: int, insight_id: str) -> None:
        if tenant_id in self._insights:
            self._insights[tenant_id].pop(insight_id, None)
