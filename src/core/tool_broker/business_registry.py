"""Business tool registry for governed Task execution via ToolBroker.

Provides a fail-secure, tenant-scoped bridge between ToolBroker action_types
(e.g. `create_task`, `list_tasks`) and the Day-2 `TaskService`. All DB access
uses the central `db_manager` so RLS and transaction lifecycle are handled
automatically.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.middleware.tenant_context import set_tenant_id
from src.core.tool_broker.exceptions import ToolExecutionException
from src.domains.tasks.schemas import TaskCreate, TaskRead, TaskUpdate


def _default_task_service_factory(
    db: AsyncSession, tenant_id: int
) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Default factory: instantiate the real TaskService."""
    from src.domains.tasks.service import TaskService

    return TaskService(db=db, tenant_id=tenant_id)


@asynccontextmanager
async def _default_session_factory() -> AsyncGenerator[AsyncSession, None]:
    """Default session factory using the central DB manager (RLS-aware)."""
    from src.core.database.database import db_manager

    async with db_manager.get_session() as session:
        yield session


class BusinessToolRegistry:
    """Registry that executes governed business actions backed by `TaskService`.

    The registry is intentionally independent of the Council / Copilot layer.
    It only knows how to turn a ToolBroker payload into a tenant-scoped
    `TaskService` call and return a structured result dict.
    """

    # Tool names recognized as governed business actions.
    # delete_task is HIGH risk (HITL-gated via ToolBrokerService); update_task is medium.
    _TOOL_NAMES = {"create_task", "list_tasks", "update_task", "delete_task"}

    def __init__(
        self,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None,
        task_service_factory: Callable[[AsyncSession, int], Any] | None = None,
    ) -> None:
        self._session_factory = session_factory or _default_session_factory
        self._task_service_factory = task_service_factory or _default_task_service_factory

    @classmethod
    def known_tool_names(cls) -> set[str]:
        """Return the set of tool names handled by this registry."""
        return set(cls._TOOL_NAMES)

    @staticmethod
    def _extract_tenant_id(
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> int:
        raw = payload.get("tenant_id")
        if raw is None:
            raise ToolExecutionException(
                tool_name="business_tool",
                error_detail="tenant_id is required in tool payload/context",
            )
        try:
            return int(raw)
        except (TypeError, ValueError) as exc:
            raise ToolExecutionException(
                tool_name="business_tool",
                error_detail=f"tenant_id must be an integer, got {type(raw).__name__}",
            ) from exc

    async def execute_business_tool(
        self,
        tool_name: str,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Dispatch a business action to the appropriate TaskService method."""
        tenant_id = self._extract_tenant_id(payload)

        # Set the tenant ContextVar so db_manager.get_session() applies RLS.
        set_tenant_id(tenant_id)

        if tool_name == "create_task":
            return await self._handle_create_task(payload, tenant_id)
        if tool_name == "list_tasks":
            return await self._handle_list_tasks(payload, tenant_id)
        if tool_name == "update_task":
            return await self._handle_update_task(payload, tenant_id)
        if tool_name == "delete_task":
            return await self._handle_delete_task(payload, tenant_id)

        raise ToolExecutionException(
            tool_name=tool_name,
            error_detail=f"Business tool '{tool_name}' is not implemented",
        )

    def _clean_task_data(
        self,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Remove injected context keys and any disallowed fields from payload."""
        disallowed = {"tenant_id", "user_id", "decision_id", "id"}
        return {k: v for k, v in payload.items() if k not in disallowed}

    async def _handle_create_task(
        self,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        tenant_id: int,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        data = self._clean_task_data(payload)
        try:
            task_in = TaskCreate(**data)
        except Exception as exc:
            raise ToolExecutionException(
                tool_name="create_task",
                error_detail=f"Invalid task data: {exc}",
            ) from exc

        async with self._session_factory() as session:
            service = self._task_service_factory(session, tenant_id)
            task = await service.create(task_in)
            await self._audit(
                session, tenant_id, "task_created", task.id, fields_changed=list(data.keys())
            )
            return {
                "success": True,
                "data": task.model_dump(),
            }

    def _extract_int(
        self,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        key: str,
        default: int,
        min_value: int | None = None,
        max_value: int | None = None,
    ) -> int:
        """Parse an integer payload field with clear validation errors."""
        raw = payload.get(key, default)
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ToolExecutionException(
                tool_name="list_tasks",
                error_detail=f"{key} must be an integer, got {type(raw).__name__}",
            ) from exc
        if min_value is not None and value < min_value:
            raise ToolExecutionException(
                tool_name="list_tasks",
                error_detail=f"{key} must be >= {min_value}, got {value}",
            )
        if max_value is not None and value > max_value:
            raise ToolExecutionException(
                tool_name="list_tasks",
                error_detail=f"{key} must be <= {max_value}, got {value}",
            )
        return value

    async def _handle_list_tasks(
        self,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        tenant_id: int,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        status = payload.get("status")
        assigned_agent_id = payload.get("assigned_agent_id")
        skip = self._extract_int(payload, "skip", 0, min_value=0)
        limit = self._extract_int(payload, "limit", 100, min_value=1, max_value=1000)

        async with self._session_factory() as session:
            service = self._task_service_factory(session, tenant_id)
            tasks = await service.list(
                status=status,
                assigned_agent_id=assigned_agent_id,
                skip=skip,
                limit=limit,
            )
            return {
                "success": True,
                "data": [t.model_dump() for t in tasks],
                "count": len(tasks),
            }

    def _extract_task_id(
        self,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        tool_name: str,
    ) -> UUID:
        """Parse and validate task_id from the payload as a UUID.

        Raises a structured ToolExecutionException (never a bare 500) so an
        attacker-controlled task_id cannot surface a stack trace.
        """
        raw = payload.get("task_id")
        if raw is None:
            raise ToolExecutionException(
                tool_name=tool_name,
                error_detail="task_id is required",
            )
        try:
            return UUID(str(raw))
        except (TypeError, ValueError) as exc:
            raise ToolExecutionException(
                tool_name=tool_name,
                error_detail="task_id must be a valid UUID",
            ) from exc

    async def _handle_update_task(
        self,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        tenant_id: int,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        task_id = self._extract_task_id(payload, "update_task")
        data = self._clean_task_data(payload)
        # task_id and the HITL ticket ref are control fields, not task attributes.
        data.pop("task_id", None)
        data.pop("_hitl_ticket_ref", None)
        try:
            task_in = TaskUpdate(**data)
        except Exception as exc:
            raise ToolExecutionException(
                tool_name="update_task",
                error_detail=f"Invalid task data: {exc}",
            ) from exc

        async with self._session_factory() as session:
            service = self._task_service_factory(session, tenant_id)
            task = await service.update(task_id, task_in)
            if task is None:
                # None covers both "does not exist" and "belongs to another tenant":
                # a fixed, generic message avoids leaking cross-tenant existence.
                raise ToolExecutionException(
                    tool_name="update_task",
                    error_detail="Task not found",
                )
            await self._audit(
                session,
                tenant_id,
                "task_updated",
                task_id,
                fields_changed=list(task_in.model_dump(exclude_unset=True).keys()),
            )
            return {"success": True, "data": task.model_dump()}

    async def _handle_delete_task(
        self,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        tenant_id: int,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        task_id = self._extract_task_id(payload, "delete_task")
        async with self._session_factory() as session:
            service = self._task_service_factory(session, tenant_id)
            deleted = await service.delete(task_id)
            if deleted:
                await self._audit(session, tenant_id, "task_deleted", task_id)
            return {"success": True, "data": {"deleted": deleted}}

    async def _audit(
        self,
        session: AsyncSession,
        tenant_id: int,
        action: str,
        task_id: Any,  # TODO(TYPE): replace Any with concrete type
        fields_changed: list[str] | None = None,
    ) -> None:
        """Write an ADR-019 audit-hash-chain entry for a business action.

        Best-effort (never blocks the primary action). Only non-sensitive
        metadata is recorded: the task id and the names of changed fields --
        never field values, which may contain PII.
        """
        # Lazy imports keep the tool_broker import graph free of governance/audit
        # deps (DSM architecture boundary).
        from src.core.governance.audit import AuditService
        from src.core.utils.best_effort import best_effort

        details: dict[str, Any] = {"task_id": str(task_id)}
        if fields_changed is not None:
            details["fields_changed"] = sorted(fields_changed)

        async with best_effort(f"business tool audit: {action}", db_session=session):
            await AuditService.log_action(
                tenant_id=tenant_id,
                action=action,
                resource=f"task:{task_id}",
                session=session,
                details=details,
                event_type="business_tool_action",
            )
            await session.commit()
