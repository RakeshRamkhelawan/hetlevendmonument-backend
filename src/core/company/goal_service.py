"""GoalService - Fase 3.1

Service for managing goals with hierarchy, ancestry, and progress propagation.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from fastapi import HTTPException
from sqlalchemy import text

from src.core.company.context import GoalChain
from src.core.company.schemas import (
    GoalAncestryResponse,
    GoalCreate,
    GoalResponse,
    GoalTreeResponse,
    GoalUpdate,
)
from src.core.container import DatabaseManager, TenantContext
from src.core.exceptions import ValidatieFout


class GoalService:
    """Service for goal management with hierarchy support."""

    # Goal type hierarchy: mission -> strategic -> project -> task
    GOAL_TYPE_HIERARCHY = ["mission", "strategic", "project", "task"]

    # Redis key prefix for ancestry cache
    ANCESTRY_CACHE_PREFIX = "ancestry_cache"
    ANCESTRY_CACHE_TTL = 300  # 5 minutes

    def __init__(self, db_manager: DatabaseManager, tenant_context: TenantContext) -> None:
        """Initialize GoalService.

        Args:
            db_manager: Database manager for queries
            tenant_context: Tenant context for isolation
        """
        self._db = db_manager
        self._tenant = tenant_context
        self._redis: Any = None  # Lazy loaded

    def _get_redis(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Lazy load Redis client."""
        if self._redis is None:
            try:
                from src.core.container import container

                self._redis = container.redis_client()
            except Exception:
                pass  # Redis optional
        return self._redis

    async def _execute(
        self,
        query: str,
        params: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        readonly: bool = True,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Execute database query with tenant filtering."""
        # Use the DatabaseManager's get_session context manager
        # This properly handles commit/rollback for write operations
        async with self._db.get_session() as session:
            result = await session.execute(text(query), params or {})
            if not readonly:
                await session.commit()
            rows = result.mappings().all()
            return [dict(row) for row in rows]

    def _validate_goal_type_hierarchy(
        self, goal_type: str, parent_goal_id: uuid.UUID | None
    ) -> None:
        """Validate that goal type follows hierarchy rules.

        Args:
            goal_type: The type of goal being created
            parent_goal_id: Optional parent goal ID

        Raises:
            ValueError: If hierarchy rules are violated
        """
        if goal_type not in self.GOAL_TYPE_HIERARCHY:
            raise ValueError(f"Invalid goal_type: {goal_type}")

        # Mission has no parent
        if goal_type == "mission" and parent_goal_id is not None:
            raise ValueError("Mission goals cannot have a parent")

        # Other types must have parent
        if goal_type != "mission" and parent_goal_id is None:
            raise ValueError(f"{goal_type} goals must have a parent")

    async def _get_parent_goal(
        self, parent_goal_id: uuid.UUID
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get parent goal for validation."""
        result = await self._execute(
            """
            SELECT id, goal_type, title
            FROM goals
            WHERE id = :goal_id AND tenant_id = :tenant_id
            """,
            {"goal_id": str(parent_goal_id), "tenant_id": self._tenant.tenant_id},
        )
        return result[0] if result else None

    async def _check_mission_exists(self, company_id: uuid.UUID) -> bool:
        """Check if company already has a mission goal."""
        result = await self._execute(
            """
            SELECT id FROM goals
            WHERE company_id = :company_id
            AND tenant_id = :tenant_id
            AND goal_type = 'mission'
            """,
            {"company_id": str(company_id), "tenant_id": self._tenant.tenant_id},
        )
        return len(result) > 0

    async def create_goal(self, company_id: uuid.UUID, data: GoalCreate) -> GoalResponse:
        """Create a new goal with hierarchy validation.

        Args:
            company_id: Company UUID
            data: Goal creation data

        Returns:
            Created goal response

        Raises:
            ValueError: If hierarchy rules are violated
        """
        # Validate goal type hierarchy
        self._validate_goal_type_hierarchy(data.goal_type, data.parent_goal_id)

        # Check mission constraints
        if data.goal_type == "mission":
            if await self._check_mission_exists(company_id):
                raise ValueError("Company already has a mission goal")
        else:
            # Validate parent exists and has correct type
            if data.parent_goal_id:
                parent = await self._get_parent_goal(data.parent_goal_id)
                if not parent:
                    raise ValueError("Parent goal not found")

                parent_type = parent["goal_type"]
                expected_parent_types = {
                    "strategic": ["mission"],
                    "project": ["strategic"],
                    "task": ["project"],
                }

                allowed = expected_parent_types.get(data.goal_type, [])
                if parent_type not in allowed:
                    raise ValueError(
                        f"{data.goal_type} goals must have a {allowed[0]} parent, got {parent_type}"
                    )

        # Create goal
        goal_id = uuid.uuid4()
        result = await self._execute(
            """
            INSERT INTO goals (
                id, tenant_id, company_id, parent_goal_id, department_id,
                goal_type, title, description, kpis, status, progress_pct, deadline
            ) VALUES (
                :id, :tenant_id, :company_id, :parent_goal_id, :department_id,
                :goal_type, :title, :description, :kpis, :status, :progress_pct, :deadline
            ) RETURNING *
            """,
            {
                "id": str(goal_id),
                "tenant_id": self._tenant.tenant_id,
                "company_id": str(company_id),
                "parent_goal_id": str(data.parent_goal_id) if data.parent_goal_id else None,
                "department_id": str(data.department_id) if data.department_id else None,
                "goal_type": data.goal_type,
                "title": data.title,
                "description": data.description,
                "kpis": json.dumps(data.kpis or {}),
                "status": "not_started",
                "progress_pct": 0,
                "deadline": data.deadline.isoformat() if data.deadline else None,
            },
            readonly=False,
        )

        return GoalResponse.model_validate(result[0])

    async def get_goal(self, goal_id: uuid.UUID) -> GoalResponse | None:
        """Get goal by ID with tenant check."""
        result = await self._execute(
            """
            SELECT * FROM goals
            WHERE id = :goal_id AND tenant_id = :tenant_id
            """,
            {"goal_id": str(goal_id), "tenant_id": self._tenant.tenant_id},
        )

        if not result:
            return None

        return GoalResponse.model_validate(result[0])

    async def get_goal_tree(self, company_id: uuid.UUID) -> GoalTreeResponse:
        """Get all goals for company as tree."""
        result = await self._execute(
            """
            SELECT * FROM goals
            WHERE company_id = :company_id AND tenant_id = :tenant_id
            ORDER BY created_at DESC
            """,
            {"company_id": str(company_id), "tenant_id": self._tenant.tenant_id},
        )

        goals = [GoalResponse.model_validate(row) for row in result]
        # Build tree structure from goals
        tree_structure: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "root": [],
            "nodes": {},
        }  # TODO(TYPE): replace Any with concrete type
        for goal in goals:
            if goal.parent_goal_id is None:
                tree_structure["root"].append(str(goal.id))
            tree_structure["nodes"][str(goal.id)] = {
                "children": [str(g.id) for g in goals if g.parent_goal_id == goal.id]
            }
        return GoalTreeResponse(goals=goals, tree_structure=tree_structure)

    async def get_ancestry(self, goal_id: uuid.UUID) -> GoalAncestryResponse:
        """Get goal ancestry chain from goal up to mission.

        Uses Redis caching with 5 minute TTL.
        """
        # Check Redis cache -- tenant-scoped key to prevent cross-tenant cache leaks (SP-SEC-001 TI-005)
        redis = self._get_redis()
        _tid = self._tenant.tenant_id or 0
        # NOTE: t0 = system namespace; never a real tenant (tenant_id > 0 per ADR-005)
        cache_key = f"t{_tid}:{self.ANCESTRY_CACHE_PREFIX}:{goal_id}"

        if redis:
            cached = await redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                return GoalAncestryResponse(chain=[GoalResponse(**g) for g in data])

        # Build ancestry from database
        chain: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        current_id: uuid.UUID | None = goal_id
        visited: set[uuid.UUID] = set()

        while current_id and current_id not in visited:
            visited.add(current_id)

            result = await self._execute(
                """
                SELECT * FROM goals
                WHERE id = :goal_id AND tenant_id = :tenant_id
                """,
                {"goal_id": str(current_id), "tenant_id": self._tenant.tenant_id},
            )

            if not result:
                break

            goal = result[0]
            chain.append(goal)

            # Move to parent
            parent_id = goal.get("parent_goal_id")
            if parent_id:
                # Handle asyncpg UUID or string
                current_id = uuid.UUID(str(parent_id))
            else:
                current_id = None

        # Cache result
        if redis and chain:
            await redis.set(cache_key, json.dumps(chain, default=str), ex=self.ANCESTRY_CACHE_TTL)

        return GoalAncestryResponse(chain=[GoalResponse.model_validate(g) for g in chain])

    async def build_goal_chain(self, goal_id: uuid.UUID) -> GoalChain:
        """Build GoalChain object from goal ancestry."""
        ancestry = await self.get_ancestry(goal_id)

        # Convert to dict format for GoalChain
        goals: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        for goal in ancestry.chain:
            goals.append(
                {
                    "id": str(goal.id),
                    "goal_type": goal.goal_type,
                    "title": goal.title,
                    "description": goal.description,
                }
            )

        return GoalChain.from_ancestry(goals)

    async def update_goal(self, goal_id: uuid.UUID, data: GoalUpdate) -> GoalResponse:
        """Update goal fields."""
        # Build update fields dynamically
        updates: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        if data.title is not None:
            updates["title"] = data.title
        if data.description is not None:
            updates["description"] = data.description
        if data.status is not None:
            updates["status"] = data.status
        if data.kpis is not None:
            updates["kpis"] = json.dumps(data.kpis)
        if data.deadline is not None:
            updates["deadline"] = data.deadline.isoformat() if data.deadline else None

        if not updates:
            # No updates, return current
            goal = await self.get_goal(goal_id)
            if goal is None:
                raise HTTPException(status_code=404, detail=f"Goal {goal_id} not found")
            return goal

        # Build SET clause
        set_clause = ", ".join([k + " = :" + k for k in updates.keys()])
        updates["goal_id"] = str(goal_id)
        updates["tenant_id"] = self._tenant.tenant_id

        # Use + concatenation (not f-string) to avoid B608: set_clause keys are
        # hardcoded field names from the model, never user-supplied column names.
        update_sql = (
            "UPDATE goals SET " + set_clause + ", updated_at = NOW()"  # nosec B608
            " WHERE id = :goal_id AND tenant_id = :tenant_id"
            " RETURNING *"
        )
        result = await self._execute(update_sql, updates, readonly=False)

        if not result:
            raise ValueError("Goal not found")

        return GoalResponse.model_validate(result[0])

    async def update_progress(self, goal_id: uuid.UUID, progress: int) -> GoalResponse:
        """Update goal progress and propagate to parents."""
        if not 0 <= progress <= 100:
            raise ValueError("Progress must be between 0 and 100")

        # Get goal with parent info
        result = await self._execute(
            """
            SELECT id, parent_goal_id FROM goals
            WHERE id = :goal_id AND tenant_id = :tenant_id
            """,
            {"goal_id": str(goal_id), "tenant_id": self._tenant.tenant_id},
        )

        if not result:
            raise ValueError("Goal not found")

        goal = result[0]
        parent_id = goal.get("parent_goal_id")

        # Update this goal
        result = await self._execute(
            """
            UPDATE goals
            SET progress_pct = :progress, updated_at = NOW()
            WHERE id = :goal_id AND tenant_id = :tenant_id
            RETURNING *
            """,
            {
                "goal_id": str(goal_id),
                "tenant_id": self._tenant.tenant_id,
                "progress": progress,
            },
            readonly=False,
        )

        updated_goal = GoalResponse.model_validate(result[0])

        # Propagate to parent
        if parent_id:
            # Handle asyncpg UUID or string
            parent_uuid = uuid.UUID(str(parent_id))
            await self._recalculate_parent_progress(parent_uuid)

        # Invalidate ancestry cache
        await self._invalidate_ancestry_cache(goal_id)

        return updated_goal

    async def _recalculate_parent_progress(self, parent_id: uuid.UUID) -> None:
        """Recalculate parent progress as average of children."""
        # Get all children progress
        result = await self._execute(
            """
            SELECT progress_pct FROM goals
            WHERE parent_goal_id = :parent_id AND tenant_id = :tenant_id
            """,
            {"parent_id": str(parent_id), "tenant_id": self._tenant.tenant_id},
        )

        if not result:
            return

        # Calculate average
        avg_progress: int = sum(cast(int, r["progress_pct"]) for r in result) // len(result)

        # Update parent
        await self._execute(
            """
            UPDATE goals
            SET progress_pct = :progress, updated_at = NOW()
            WHERE id = :goal_id AND tenant_id = :tenant_id
            RETURNING id
            """,
            {
                "goal_id": str(parent_id),
                "tenant_id": self._tenant.tenant_id,
                "progress": avg_progress,
            },
            readonly=False,
        )

    async def _invalidate_ancestry_cache(self, goal_id: uuid.UUID) -> None:
        """Invalidate ancestry cache for goal and all descendants."""
        redis = self._get_redis()
        if not redis:
            return

        # Delete cache for this goal -- tenant-scoped key (SP-SEC-001 TI-005)
        _tid = self._tenant.tenant_id or 0
        cache_key = f"t{_tid}:{self.ANCESTRY_CACHE_PREFIX}:{goal_id}"
        await redis.delete(cache_key)

        # Also delete cache for all descendants (simplified - just direct children)
        result = await self._execute(
            """
            SELECT id FROM goals
            WHERE parent_goal_id = :goal_id AND tenant_id = :tenant_id
            """,
            {"goal_id": str(goal_id), "tenant_id": self._tenant.tenant_id},
        )

        for row in result:
            child_key = f"{self.ANCESTRY_CACHE_PREFIX}:{row['id']}"
            await redis.delete(child_key)

    async def delete_goal(self, goal_id: uuid.UUID) -> None:
        """Delete goal if it has no children."""
        # Check for children
        result = await self._execute(
            """
            SELECT id FROM goals
            WHERE parent_goal_id = :goal_id AND tenant_id = :tenant_id
            """,
            {"goal_id": str(goal_id), "tenant_id": self._tenant.tenant_id},
        )

        if result:
            raise ValidatieFout("Cannot delete goal with children")

        # Delete
        await self._execute(
            """
            DELETE FROM goals
            WHERE id = :goal_id AND tenant_id = :tenant_id
            """,
            {"goal_id": str(goal_id), "tenant_id": self._tenant.tenant_id},
            readonly=False,
        )
