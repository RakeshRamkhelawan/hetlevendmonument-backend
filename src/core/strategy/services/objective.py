"""Objective Management Service."""

import logging
from typing import Any, Optional

from src.core.strategy.types import StrategicObjective, StrategicPriority

logger = logging.getLogger(__name__)


class ObjectiveService:
    """Service for managing strategic objectives."""

    def __init__(
        self,
        tenant_id: int | None = None,
        repository: Any | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        self.tenant_id = tenant_id
        self._repository = repository
        self.objectives: dict[str, StrategicObjective] = {}

    async def add(self, objective: StrategicObjective) -> None:
        """Add a new strategic objective with transactional consistency."""
        # P1 FIX: Write-ahead pattern - persist to DB first
        if self._repository and self.tenant_id is not None:
            try:
                await self._repository.save_objective(self.tenant_id, objective)
            except Exception as exc:
                logger.error("Failed to persist objective %s: %s", objective.id, exc)
                raise RuntimeError(f"Failed to persist objective: {exc}") from exc

        # Only update in-memory state AFTER successful DB write
        self.objectives[objective.id] = objective
        logger.info("Strategic objective added: %s (%s)", objective.title, objective.id)

    async def update(self, objective_id: str, **updates: Any) -> StrategicObjective | None:  # TODO(TYPE): replace Any with concrete type
        """Update an existing objective."""
        obj = self.objectives.get(objective_id)
        if not obj:
            return None

        # Update fields
        for key, value in updates.items():
            if hasattr(obj, key):
                setattr(obj, key, value)

        # Persist update
        if self._repository and self.tenant_id is not None:
            try:
                await self._repository.save_objective(self.tenant_id, obj)
            except Exception as exc:
                logger.error("Failed to update objective %s: %s", objective_id, exc)
                raise RuntimeError(f"Failed to update objective: {exc}") from exc

        return obj

    async def remove(self, objective_id: str) -> bool:
        """Remove an objective."""
        if objective_id not in self.objectives:
            return False

        # Delete from persistence
        if self._repository and self.tenant_id is not None:
            try:
                await self._repository.delete_objective(self.tenant_id, objective_id)
            except Exception as exc:
                logger.error("Failed to delete objective %s: %s", objective_id, exc)
                raise RuntimeError(f"Failed to delete objective: {exc}") from exc

        del self.objectives[objective_id]
        logger.info("Strategic objective removed: %s", objective_id)
        return True

    def get(self, objective_id: str) -> StrategicObjective | None:
        """Get a specific objective by ID."""
        return self.objectives.get(objective_id)

    def list_all(self) -> list[StrategicObjective]:
        """List all objectives."""
        return list(self.objectives.values())

    def list_active(self) -> list[StrategicObjective]:
        """List active objectives."""
        return [obj for obj in self.objectives.values() if obj.status == "active"]

    def list_by_priority(self, priority: StrategicPriority) -> list[StrategicObjective]:
        """List objectives by priority."""
        return [obj for obj in self.objectives.values() if obj.priority == priority]

    def update_progress(self, objective_id: str, progress: float) -> StrategicObjective | None:
        """Update progress for an objective."""
        obj = self.objectives.get(objective_id)
        if obj:
            obj.progress = max(0.0, min(1.0, progress))
            if obj.progress >= 1.0:
                obj.status = "completed"
        return obj

    async def load_from_repository(self) -> None:
        """Load objectives from repository."""
        if self._repository is None or self.tenant_id is None:
            return

        try:
            objectives = await self._repository.get_active_objectives(self.tenant_id)
            self.objectives.clear()
            for obj in objectives:
                self.objectives[obj.id] = obj
            logger.info(
                "Loaded %d objectives for tenant %s",
                len(self.objectives),
                self.tenant_id,
            )
        except Exception as exc:
            logger.error("Failed to load objectives: %s", exc)
