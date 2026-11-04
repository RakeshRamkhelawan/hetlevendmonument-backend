"""
ActivePieces Service Layer

Application Service for ActivePieces integration.
Handles business logic for Flow management, Connection management, and Piece synchronization.
"""

from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from fastapi import Depends
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.activepieces.client import UITVOERFOUT, ActivePiecesClient, ap_client_voor
from src.core.activepieces.stappencontrole import NietToegestaneStap, controleer_graaf
from src.core.activepieces.repositories import (
    ActivePiecesConnectionRepository,
    ActivePiecesFlowRepository,
    ActivePiecesFlowRunRepository,
    ActivePiecesSyncLogRepository,
)
from src.core.activepieces.schemas import (
    ConnectionCreate,
    ConnectionRead,
    FlowRead,
    FlowRunRead,
    PieceRead,
)
from src.core.activepieces.validator import (
    ValidationResult,
    validate_connection,
    validate_flow,
    validate_react_flow,
)
from src.core.activepieces.verbinding import ApVerbindingOntbreektError
from src.core.database.database import get_db
from src.core.exceptions import ValidatieFout
from src.core.middleware.tenant_context import get_tenant_id


class _ActivePiecesClientProtocol(Protocol):
    """Structural interface for ActivePieces client implementations.

    Both :class:`ActivePiecesClient` and :class:`_DisabledActivePiecesClient`
    satisfy this protocol, allowing the service layer to work with either
    without ``cast()`` or ``Any``.  # TODO(TYPE): replace Any with concrete type
    """

    def is_available(self) -> bool: ...

    def eigen_project(self, project_id: str | None) -> str: ...

    async def health_check(
        self, *args: Any, **kwargs: Any
    ) -> dict[
        # TODO(TYPE): replace Any with concrete type
        str, Any
    ]: ...  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type

    async def list_pieces(self) -> list[PieceRead]: ...

    async def list_project_flows(
        self, project_id: str
    ) -> list[dict[str, Any]]: ...  # TODO(TYPE): replace Any with concrete type

    async def create_flow(
        self, *args: Any, **kwargs: Any
    ) -> dict[
        # TODO(TYPE): replace Any with concrete type
        str, Any
    ]: ...  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type

    async def update_flow(
        self, *args: Any, **kwargs: Any
    ) -> dict[
        # TODO(TYPE): replace Any with concrete type
        str, Any
    ]: ...  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type

    async def delete_flow(self, *args: Any, **kwargs: Any) -> bool: ...

    async def build_flow_definition(
        self, react_flow_data: dict[str, object]
    ) -> dict[str, object]: ...

    async def trigger_flow(
        self,
        flow_id: str,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]: ...  # TODO(TYPE): replace Any with concrete type

    async def retry_run(self, run_id: str) -> dict[str, object]: ...

    async def get_flow(self, flow_id: str) -> dict[str, object]: ...

    async def get_connection(self, connection_id: str) -> dict[str, object]: ...

    async def get_run_logs(
        self, run_id: str
    ) -> dict[str, Any]: ...  # TODO(TYPE): replace Any with concrete type

    async def list_runs(
        self, flow_id: str, limit: int
    ) -> list[dict[str, Any]]: ...  # TODO(TYPE): replace Any with concrete type

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        operation_name: str,
        json_data: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        params: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]: ...  # TODO(TYPE): replace Any with concrete type


class _DisabledActivePiecesClient:
    """Stub client used when ActivePieces is not configured."""

    def eigen_project(self, project_id: str | None) -> str:
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")

    async def list_pieces(self) -> list[PieceRead]:
        logger.debug("ActivePieces is unconfigured: returning empty piece list")
        return []

    async def get_piece(self, *args: Any, **kwargs: Any) -> PieceRead | None:
        logger.debug("ActivePieces is unconfigured: get_piece returning None")
        return None

    async def list_flows(
        self, *args: Any, **kwargs: Any
    ) -> list[
        # TODO(TYPE): replace Any with concrete type
        dict[str, Any]
    ]:  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        logger.debug("ActivePieces is unconfigured: list_flows returning empty list")
        return []

    async def get_flow(
        self, *args: Any, **kwargs: Any
    ) -> dict[
        # TODO(TYPE): replace Any with concrete type
        str, Any
    ]:  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")

    async def create_flow(
        self, *args: Any, **kwargs: Any
    ) -> dict[
        # TODO(TYPE): replace Any with concrete type
        str, Any
    ]:  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")

    async def update_flow(
        self, *args: Any, **kwargs: Any
    ) -> dict[
        # TODO(TYPE): replace Any with concrete type
        str, Any
    ]:  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")

    async def delete_flow(self, *args: Any, **kwargs: Any) -> bool:
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")

    async def build_flow_definition(
        self, react_flow_data: dict[str, object]
    ) -> dict[str, object]:
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")

    async def toggle_flow(
        self, *args: Any, **kwargs: Any
    ) -> dict[
        # TODO(TYPE): replace Any with concrete type
        str, Any
    ]:  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")

    async def validate_flow(
        self, *args: Any, **kwargs: Any
    ) -> dict[
        # TODO(TYPE): replace Any with concrete type
        str, Any
    ]:  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")

    async def execute_flow(
        self, *args: Any, **kwargs: Any
    ) -> dict[
        # TODO(TYPE): replace Any with concrete type
        str, Any
    ]:  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")

    async def list_flow_runs(
        self, *args: Any, **kwargs: Any
    ) -> list[
        # TODO(TYPE): replace Any with concrete type
        dict[str, Any]
    ]:  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        logger.debug("ActivePieces is unconfigured: list_flow_runs returning empty list")
        return []

    async def get_flow_run(
        self, *args: Any, **kwargs: Any
    ) -> dict[
        # TODO(TYPE): replace Any with concrete type
        str, Any
    ]:  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")

    async def retry_flow_run(
        self, *args: Any, **kwargs: Any
    ) -> dict[
        # TODO(TYPE): replace Any with concrete type
        str, Any
    ]:  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")

    async def cancel_flow_run(
        self, *args: Any, **kwargs: Any
    ) -> dict[
        # TODO(TYPE): replace Any with concrete type
        str, Any
    ]:  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")

    async def list_connections(
        self, *args: Any, **kwargs: Any
    ) -> list[
        # TODO(TYPE): replace Any with concrete type
        dict[str, Any]
    ]:  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        logger.debug("ActivePieces is unconfigured: list_connections returning empty list")
        return []

    async def get_connection(
        self, *args: Any, **kwargs: Any
    ) -> dict[
        # TODO(TYPE): replace Any with concrete type
        str, Any
    ]:  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")

    async def create_connection(
        self, *args: Any, **kwargs: Any
    ) -> dict[
        # TODO(TYPE): replace Any with concrete type
        str, Any
    ]:  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")

    async def update_connection(
        self, *args: Any, **kwargs: Any
    ) -> dict[
        # TODO(TYPE): replace Any with concrete type
        str, Any
    ]:  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")

    async def delete_connection(self, *args: Any, **kwargs: Any) -> bool:
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")

    async def test_connection(
        self, *args: Any, **kwargs: Any
    ) -> dict[
        # TODO(TYPE): replace Any with concrete type
        str, Any
    ]:  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        return {"success": False, "message": "ActivePieces not configured"}

    async def health_check(
        self, *args: Any, **kwargs: Any
    ) -> dict[
        # TODO(TYPE): replace Any with concrete type
        str, Any
    ]:  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        return {"is_available": False, "api_reachable": False}

    def is_available(self) -> bool:
        return False

    async def list_project_flows(
        self, project_id: str
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        logger.debug("ActivePieces is unconfigured: list_project_flows returning empty list")
        return []

    async def trigger_flow(
        self,
        flow_id: str,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "execution_id": "",
            "status": "DISABLED",
            "start_time": "",
            "duration": 0,
            "project_id": "",
            "flow_id": flow_id,
        }

    async def retry_run(self, run_id: str) -> dict[str, object]:
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")

    async def get_run_logs(
        self, run_id: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")

    async def list_runs(
        self, flow_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        logger.debug("ActivePieces is unconfigured: list_runs returning empty list")
        return []

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        operation_name: str,
        json_data: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        params: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        raise RuntimeError("ActivePieces client is disabled: configure ACTIVEPIECES_API_KEY")


_AP_PIECE_VOORVOEGSEL = "@activepieces/piece-"
# 100 per pagina is gemeten toegestaan (limit=500 gaf ook 200); de bovengrens van 50 pagina's
# voorkomt dat een cursor die nooit eindigt de aanvraag eindeloos laat doorlopen.
_PAGINAGROOTTE = 100
_MAX_PAGINAS = 50


def _ap_piece_naam(app_name: str) -> str:
    """De naam die AP voor een piece gebruikt: `slack` wordt `@activepieces/piece-slack`."""
    return app_name if app_name.startswith("@") else f"{_AP_PIECE_VOORVOEGSEL}{app_name}"


def _korte_piece_naam(piece_name: object) -> str:
    naam = str(piece_name or "")
    return naam.removeprefix(_AP_PIECE_VOORVOEGSEL)


def _alleen_in_project(verbinding: dict[str, object], project_id: str) -> bool:
    """Staat deze AP-verbinding in dit project EN in geen ander? (AP geeft een lijst `projectIds`)."""
    return verbinding.get("projectIds") == [project_id]


def _naar_connection_read(item: dict[str, object], project_id: str) -> ConnectionRead:
    """Een AP-verbinding als `ConnectionRead`, zonder sleutel."""
    return ConnectionRead.model_validate(
        {
            "id": item["id"],
            "name": item.get("displayName", ""),
            "app_name": _korte_piece_naam(item.get("pieceName")),
            "project_id": project_id,
            "value": {},  # Don't expose credentials
            "created": item.get("created", ""),
            "updated": item.get("updated", ""),
        }
    )


class ActivePiecesService:
    """
    Application Service for ActivePieces integration.
    Handles business logic for Flow management and Piece synchronization.
    """

    def __init__(
        self,
        client: Any = None,
        db: AsyncSession | None = None,
    ) -> None:
        # FastAPI injects the client of the tenant (`get_activepieces_client`). Zonder client is er
        # geen verbinding voor deze aanroeper, en dan is het antwoord de uitgeschakelde client --
        # nooit een algemene client die de service zelf bouwt (ADR-040 B3/B4).
        self._client: _ActivePiecesClientProtocol
        if client is not None and hasattr(client, "list_pieces"):
            self._client = client
        else:
            logger.warning("ActivePieces: geen client voor deze aanroeper, uitgeschakelde client")
            self._client = _DisabledActivePiecesClient()
        self._db = db
        self._flow_repo = ActivePiecesFlowRepository(db) if db else None
        self._conn_repo = ActivePiecesConnectionRepository(db) if db else None
        self._run_repo = ActivePiecesFlowRunRepository(db) if db else None
        self._sync_repo = ActivePiecesSyncLogRepository(db) if db else None

    # =========================================================================
    # Health & Status
    # =========================================================================

    async def check_health(self) -> bool:
        """Check if ActivePieces integration is healthy."""
        try:
            health = await self._client.health_check()
            return bool(health.get("api_reachable", False))
        except Exception:
            return False

    async def get_detailed_health(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get detailed health status."""
        return await self._client.health_check()

    # =========================================================================
    # Piece / Integration Management
    # =========================================================================

    async def sync_pieces(self) -> int:
        """
        Sync available pieces from ActivePieces to local database.
        Returns count of synced pieces.
        """
        pieces = await self._client.list_pieces()
        count = 0
        for piece in pieces:
            # Note: Pieces are fetched from ActivePieces on-demand
            # Caching in local database is handled by focus_builder piece cache
            count += 1

        logger.info("Synced {} pieces from ActivePieces", count)
        return count

    async def get_all_pieces(self) -> list[PieceRead]:
        """Get all available pieces from ActivePieces."""
        return await self._client.list_pieces()

    async def get_piece_by_name(self, piece_name: str) -> PieceRead | None:
        """Get a specific piece by name."""
        pieces = await self._client.list_pieces()
        return next((p for p in pieces if p.name == piece_name), None)

    # =========================================================================
    # Flow Management
    # =========================================================================

    async def list_flows(
        self,
        project_id: str | None = None,
        status: str | None = None,
    ) -> list[FlowRead]:
        """List all flows with optional filtering.

        Het project is dat van de verbinding van de tenant; een `project_id` van de aanroeper mag
        alleen datzelfde project zijn (anders 403), en zonder `project_id` geldt het eigen project.
        """
        if isinstance(self._client, _DisabledActivePiecesClient):
            return []
        project_id = self._client.eigen_project(project_id)

        flows = await self._client.list_project_flows(project_id)

        if status:
            flows = [f for f in flows if f.get("status") == status]

        return [
            FlowRead(
                id=f["id"],
                project_id=f.get("projectId", project_id),
                folder_id=f.get("folderId"),
                status=f.get("status", "DISABLED"),
                version_id=f.get("version", {}).get("id", ""),
                created=f.get("created", ""),
                updated=f.get("updated", ""),
            )
            for f in flows
        ]

    async def get_flow(
        self, flow_id: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get detailed flow information."""
        return await self._client.get_flow(flow_id)

    async def create_flow(
        self,
        name: str,
        project_id: str | None,
        react_flow_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        description: str | None = None,
        tenant_id: int | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Create a new flow from React Flow data.

        Args:
            name: Flow name
            project_id: ActivePieces project ID
            react_flow_data: React Flow graph definition
            description: Optional flow description

        Returns:
            Created flow data
        """
        # Validate React Flow data
        validation = validate_react_flow(react_flow_data)
        if not validation.valid:
            raise ValueError(f"Invalid React Flow data: {validation.errors}")
        # Voor het omzetten: weigeren hangt dan niet af van of AP bereikbaar is.
        controleer_graaf(react_flow_data)

        # Transform to ActivePieces format
        ap_flow = await self._client.build_flow_definition(react_flow_data)
        ap_flow["displayName"] = name
        ap_flow["description"] = description or ""

        # Validate AP flow
        flow_validation = validate_flow(ap_flow)
        if not flow_validation.valid:
            raise ValueError(f"Invalid flow definition: {flow_validation.errors}")

        # Create flow
        project_id = self._client.eigen_project(project_id)
        flow = await self._client.create_flow(project_id, ap_flow)

        logger.info("Created flow '{}' (ID: {})", name, flow.get("id"))

        if self._flow_repo and self._db and tenant_id:
            await self._flow_repo.create(
                tenant_id=tenant_id,
                ap_flow_id=flow.get("id", ""),
                project_id=project_id,
                name=name,
                description=description,
                status=flow.get("status", "DISABLED"),
                flow_definition=react_flow_data,
            )
            await self._db.commit()

        return flow

    async def update_flow(
        self,
        flow_id: str,
        name: str | None = None,
        description: str | None = None,
        react_flow_data: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        status: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Update an existing flow.

        Args:
            flow_id: Flow ID to update
            name: New name (optional)
            description: New description (optional)
            react_flow_data: New React Flow data (optional)
            status: New status (optional)

        Returns:
            Updated flow data
        """
        # Get existing flow
        existing = await self.get_flow(flow_id)

        update_data: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        if react_flow_data:
            # Validate and transform
            validation = validate_react_flow(react_flow_data)
            if not validation.valid:
                raise ValueError(f"Invalid React Flow data: {validation.errors}")
            controleer_graaf(react_flow_data)

            ap_flow = await self._client.build_flow_definition(react_flow_data)

            if name:
                ap_flow["displayName"] = name
            if description:
                ap_flow["description"] = description

            flow_validation = validate_flow(ap_flow)
            if not flow_validation.valid:
                raise ValueError(f"Invalid flow definition: {flow_validation.errors}")

            update_data = ap_flow
        else:
            # Just update metadata
            update_data = {
                "displayName": name or existing.get("version", {}).get("displayName"),
                "description": description or existing.get("version", {}).get("description"),
            }

        if status:
            update_data["status"] = status

        updated = await self._client.update_flow(flow_id, update_data)

        logger.info("Updated flow {}", flow_id)
        return updated

    async def delete_flow(
        self,
        flow_id: str,
        tenant_id: int | None = None,
    ) -> bool:
        """Delete a flow."""
        success = await self._client.delete_flow(flow_id)
        if success:
            logger.info("Deleted flow {}", flow_id)
            if self._flow_repo and self._db and tenant_id:
                local_flow = await self._flow_repo.get_by_ap_flow_id(tenant_id, flow_id)
                if local_flow:
                    await self._flow_repo.delete(tenant_id, local_flow.id)
                    await self._db.commit()
        return success

    async def toggle_flow(
        self, flow_id: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Toggle flow enabled/disabled status."""
        flow = await self.get_flow(flow_id)

        current_status = flow.get("status", "DISABLED")
        new_status = "DISABLED" if current_status == "ENABLED" else "ENABLED"

        # Via `update_flow`: daar zit de stappencontrole bij aanzetten (wfb-dag1 stap 1).
        updated = await self._client.update_flow(flow_id, {"status": new_status})

        logger.info("Toggled flow {} to {}", flow_id, new_status)
        return updated

    async def validate_flow_definition(
        self,
        flow_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        flow_type: str = "react",
    ) -> ValidationResult:
        """
        Validate a flow definition without creating it.

        Args:
            flow_data: Flow definition
            flow_type: 'react' or 'activepieces'

        Returns:
            Validation result with errors and warnings
        """
        if flow_type == "react":
            return validate_react_flow(flow_data)
        else:
            return validate_flow(flow_data)

    # =========================================================================
    # Flow Execution
    # =========================================================================

    async def execute_flow(
        self,
        flow_id: str,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        synchronous: bool = False,
        timeout_seconds: int = 60,
        tenant_id: int | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Execute a flow.

        Args:
            flow_id: Flow ID to execute
            payload: Execution payload
            synchronous: Wait for completion
            timeout_seconds: Timeout for synchronous execution

        Returns:
            Execution result
        """
        result = await self._client.trigger_flow(flow_id, payload)

        if synchronous:
            result = await self._wait_for_completion(
                result["execution_id"],
                timeout_seconds,
            )

        logger.info("Executed flow {}, run ID: {}", flow_id, result.get("execution_id"))

        if self._run_repo and self._flow_repo and self._db and tenant_id:
            local_flow = await self._flow_repo.get_by_ap_flow_id(tenant_id, flow_id)
            if local_flow:
                await self._run_repo.create(
                    tenant_id=tenant_id,
                    flow_id=local_flow.id,
                    ap_run_id=result.get("execution_id", ""),
                    project_id=local_flow.project_id,
                    status="RUNNING",
                    payload=payload,
                )
                await self._db.commit()

        return result

    async def _wait_for_completion(
        self,
        run_id: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Wait for a flow run to complete."""
        import asyncio
        from datetime import datetime, timedelta, timezone

        deadline = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)

        while datetime.now(timezone.utc) < deadline:
            run = await self._client.get_run_logs(run_id)

            status = run.get("status")
            if status in ["SUCCEEDED", "FAILED", "STOPPED"]:
                return {
                    "execution_id": run_id,
                    "final_status": status,
                    "run_details": run,
                }

            await asyncio.sleep(1)

        return {
            "execution_id": run_id,
            "final_status": "TIMEOUT",
        }

    async def get_flow_runs(
        self,
        flow_id: str,
        limit: int = 10,
    ) -> list[FlowRunRead]:
        """Get recent runs for a flow."""
        runs = await self._client.list_runs(flow_id, limit)

        return [
            FlowRunRead(
                id=r["id"],
                project_id=r.get("projectId", ""),
                flow_id=r.get("flowId", flow_id),
                status=r.get("status", "UNKNOWN"),
                start_time=r.get("startTime", ""),
                finish_time=r.get("finishTime"),
                duration=r.get("duration"),
            )
            for r in runs
        ]

    async def get_flow_run(
        self, run_id: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get details of a specific flow run."""
        return await self._client.get_run_logs(run_id)

    async def retry_flow_run(
        self, run_id: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Retry a failed flow run."""
        # Via de client: daar zit de stappencontrole op de flow van de run (wfb-dag1).
        result = await self._client.retry_run(run_id)
        logger.info("Retried run {}", run_id)
        return result

    async def cancel_flow_run(
        self, run_id: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Cancel a running flow run."""
        await self._client.get_run_logs(run_id)  # 404 als de run niet van deze tenant is
        result = await self._client._make_request("POST", f"/flow-runs/{run_id}/stop", "cancel_run")
        logger.info("Cancelled run {}", run_id)
        return result

    # =========================================================================
    # Connection Management
    # =========================================================================

    async def list_connections(
        self,
        app_name: str | None = None,
    ) -> list[ConnectionRead]:
        """List all app connections."""
        project_id = self._client.eigen_project(None)
        # AP geeft standaard 10 verbindingen met een `next`-cursor (gemeten); volg hem tot het eind.
        ruw: list[dict[str, object]] = []
        cursor: str | None = None
        for _pagina in range(_MAX_PAGINAS):
            params: dict[str, str | int] = {"projectId": project_id, "limit": _PAGINAGROOTTE}
            if cursor:
                params["cursor"] = cursor
            data = await self._client._make_request(
                "GET", "/app-connections", "list_connections", params=params
            )
            ruw.extend(cast(list[dict[str, object]], data.get("data", [])))
            volgende = data.get("next")
            if not volgende:
                break
            cursor = str(volgende)
        else:
            logger.warning("AP-verbindingenlijst afgekapt na {} pagina's", _MAX_PAGINAS)
        # Ook aan onze kant filteren: het serviceaccount ziet elk project. Een verbinding die
        # ook in een ander project staat, is niet van deze tenant (fail-closed).
        connections = [c for c in ruw if _alleen_in_project(c, project_id)]

        if app_name:
            doel = _ap_piece_naam(app_name)
            connections = [c for c in connections if c.get("pieceName") == doel]

        return [_naar_connection_read(c, project_id) for c in connections]

    async def get_connection(self, connection_id: str) -> ConnectionRead:
        """Get connection details (without sensitive data)."""
        conn = await self._client.get_connection(connection_id)
        return _naar_connection_read(conn, self._client.eigen_project(None))

    async def create_connection(self, data: ConnectionCreate) -> ConnectionRead:
        """Create a new app connection."""
        project_id = self._client.eigen_project(data.project_id)
        # Het project is dat van de tenant en komt niet van de aanroeper; de validator wil het wel.
        validation = validate_connection(data.model_copy(update={"project_id": project_id}))
        if not validation.valid:
            raise ValidatieFout(
                "De verbindingsgegevens zijn niet volledig: naam, app, project en waarde zijn verplicht."
            )
        verbindingstype = (data.value or {}).get("type")
        if not isinstance(verbindingstype, str) or not verbindingstype:
            raise ValidatieFout("Het type van de verbinding ontbreekt in de gegevens.")

        # AP maakt of vervangt op `externalId`: een eigen id per verbinding, anders overschrijft
        # een tweede verbinding met dezelfde naam de eerste.
        result = await self._client._make_request(
            "POST",
            "/app-connections",
            "create_connection",
            json_data={
                "externalId": f"ss-{uuid4().hex}",
                "displayName": data.name,
                "pieceName": _ap_piece_naam(data.app_name),
                "projectId": project_id,
                "type": verbindingstype,
                "value": data.value,
            },
        )

        logger.info("Created connection '{}' for {}", data.name, data.app_name)
        return _naar_connection_read(result, project_id)

    async def delete_connection(self, connection_id: str) -> None:
        """Delete a connection."""
        await self._client.get_connection(connection_id)  # 404 als hij niet van deze tenant is
        await self._client._make_request(
            "DELETE", f"/app-connections/{connection_id}", "delete_connection"
        )
        logger.info("Deleted connection {}", connection_id)

    async def test_connection(
        self, connection_id: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """De status van een verbinding bij AP.

        ActivePieces 0.92.1 heeft geen testroute (gemeten: 404). Dit leest dus de status en doet
        geen live-aanroep naar de dienst achter de verbinding.
        """
        conn = await self._client.get_connection(connection_id)  # 404 als niet van deze tenant
        status = str(conn.get("status", ""))
        return {
            "success": status == "ACTIVE",
            "message": f"Status bij ActivePieces: {status or 'onbekend'}",
            "details": {"live_gecontroleerd": False},
        }

    async def update_connection(
        self,
        connection_id: str,
        name: str | None = None,
        value: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> ConnectionRead:
        """Update an existing connection.

        Alleen de naam: `POST /app-connections/{id}` met `displayName`; de opgeslagen waarde blijft
        ongemoeid en een meegestuurde `value` wordt door AP genegeerd (gemeten). Een nieuwe
        sleutel gaat als upsert op hetzelfde `externalId`.
        """
        existing = await self._client.get_connection(connection_id)
        project_id = self._client.eigen_project(None)

        if value:
            # Zonder externalId zou AP een NIEUWE verbinding maken en de oude laten staan.
            if not existing.get("externalId"):
                raise ValidatieFout(
                    "Deze verbinding heeft geen vaste sleutel bij ActivePieces; maak hem opnieuw aan."
                )
            result = await self._client._make_request(
                "POST",
                "/app-connections",
                "update_connection",
                json_data={
                    "externalId": existing.get("externalId"),
                    "displayName": name or existing.get("displayName"),
                    "pieceName": existing.get("pieceName"),
                    "projectId": project_id,
                    "type": existing.get("type"),
                    "value": {**value, "type": existing.get("type")},
                },
            )
        else:
            result = await self._client._make_request(
                "POST",
                f"/app-connections/{connection_id}",
                "update_connection",
                json_data={"displayName": name or existing.get("displayName")},
            )

        logger.info("Updated connection {}", connection_id)
        return _naar_connection_read(result or existing, project_id)

    # =========================================================================
    # Tenant-Specific Operations
    # =========================================================================

    async def create_connection_for_tenant(
        self,
        tenant_id: int,
        app_name: str,
        config: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        connection_name: str | None = None,
    ) -> ConnectionRead:
        """
        Create a connection for a tenant.
        Maps tenant_id to ActivePieces project and persists a local binding.
        """
        # Get or create project for tenant
        project_id = await self._get_or_create_project_for_tenant(tenant_id)

        # Generate connection name
        name = connection_name or f"{app_name}_{tenant_id}"

        # Create connection
        data = ConnectionCreate(
            name=name,
            app_name=app_name,
            project_id=project_id,
            value=config,
        )

        result = await self.create_connection(data)

        # Persist local binding so future lookups are tenant-scoped
        if self._conn_repo is not None:
            await self._conn_repo.create(
                tenant_id=tenant_id,
                ap_connection_id=result.id,
                project_id=project_id,
                app_name=app_name,
                name=name,
            )
            if self._db is not None:
                await self._db.commit()

        return result

    async def _get_or_create_project_for_tenant(self, tenant_id: int) -> str:
        """
        Get or create an ActivePieces project for a tenant.

        Reads from local first-party binding first (fail-closed).
        Only calls the remote API to create a NEW dedicated project when
        no local binding exists -- never reuses an arbitrary first remote project.
        """
        # Het project is dat van de verbinding van de tenant (ADR-040 B3/B4); de service maakt er
        # geen aan en kiest er geen uit lokale rijen. De `tenant_id` hoort bij de client zelf.
        return self._client.eigen_project(None)

    async def get_tenant_flows(self, tenant_id: int) -> list[FlowRead]:
        """Get all flows for a specific tenant."""
        # Het project is dat van de client (de verbinding van de tenant), niet een lokale rij.
        return await self.list_flows()

    async def _get_project_for_tenant(self, tenant_id: int) -> str | None:
        """Get the ActivePieces project ID for a tenant from local bindings (fail-closed)."""
        if self._flow_repo is not None:
            flows = await self._flow_repo.list_by_tenant(tenant_id, limit=1)
            if flows:
                return str(flows[0].project_id)
        if self._conn_repo is not None:
            conns = await self._conn_repo.list_by_tenant(tenant_id)
            if conns:
                return str(conns[0].project_id)
        return None

    # =========================================================================
    # High-Level Workflow Execution
    # =========================================================================

    async def execute_workflow(
        self,
        workflow_definition: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        project_id: str | None = None,
        *,
        tenant_id: int,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        High-level workflow execution.
        Creates/updates flow and triggers execution.
        """
        if not self._client.is_available():
            logger.warning(
                "ActivePieces unavailable",
                tenant_id=tenant_id,
                fallback="local_only",
            )
            return {
                "success": False,
                "error": "Automation engine temporarily unavailable",
                "fallback": "pending_sync",
            }

        try:
            if not project_id:
                project_id = await self._get_or_create_project_for_tenant(tenant_id)

            ap_flow_definition = await self._client.build_flow_definition(workflow_definition)

            flow_name = str(ap_flow_definition.get("displayName", "unnamed"))

            # Check for existing flow
            existing_flows = await self._client.list_project_flows(project_id)
            existing_flow = next(
                (f for f in existing_flows if f.get("version", {}).get("displayName") == flow_name),
                None,
            )

            if existing_flow:
                flow = await self._client.update_flow(existing_flow["id"], ap_flow_definition)
            else:
                flow = await self._client.create_flow(project_id, ap_flow_definition)

            # Persist local flow binding for new flows
            if self._flow_repo is not None and not existing_flow:
                await self._flow_repo.create(
                    tenant_id=tenant_id,
                    ap_flow_id=flow["id"],
                    project_id=project_id,
                    name=flow_name,
                )
                if self._db is not None:
                    await self._db.commit()

            # Trigger execution
            run = await self._client.trigger_flow(
                flow["id"], {"source": "sanskritisetu", "tenant_id": tenant_id}
            )

            logger.info(
                "Workflow executed",
                flow_id=flow["id"],
                run_id=run.get("execution_id"),
                tenant_id=tenant_id,
            )

            return {
                "success": True,
                "flow_id": flow["id"],
                "run_id": run.get("execution_id"),
                "status": run.get("status", "RUNNING"),
            }

        except NietToegestaneStap:
            raise
        except Exception as e:
            logger.error(
                "Workflow execution failed", soort=type(e).__name__, tenant_id=tenant_id
            )
            return {"success": False, "error": UITVOERFOUT}


async def activepieces_service_voor(tenant_id: int | None) -> ActivePiecesService:
    """De service van EEN tenant voor code zonder verzoek (bijv. de lijst met agents).

    Zonder tenant of zonder verbinding krijgt de service de uitgeschakelde client en dus een lege
    catalogus; er komt nooit een algemene client voor in de plaats (ADR-040 B3/B4).
    """
    client: ActivePiecesClient | None = None
    if tenant_id is not None:
        try:
            client = await ap_client_voor(tenant_id)
        except ApVerbindingOntbreektError:
            logger.warning("ActivePieces: geen verbinding voor tenant {}", tenant_id)
    return ActivePiecesService(client=client)


async def get_activepieces_service(
    db: AsyncSession = Depends(get_db),
    tenant_id: int | None = Depends(get_tenant_id),
) -> ActivePiecesService:
    """FastAPI dependency: de service met de database en de client van de tenant uit het token.

    Heeft de tenant geen verbinding (of is er geen tenant), dan krijgt de service de
    uitgeschakelde client: de catalogus is dan leeg en elke schrijfactie faalt. Er komt NOOIT een
    algemene client voor in de plaats (ADR-040 B3/B4).
    """
    client: ActivePiecesClient | None = None
    if tenant_id is not None:
        try:
            client = await ap_client_voor(tenant_id, db)
        except ApVerbindingOntbreektError:
            logger.warning("ActivePieces: geen verbinding voor tenant {}", tenant_id)
    return ActivePiecesService(client=client, db=db)
