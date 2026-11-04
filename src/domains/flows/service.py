import logging
from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from src.core.activepieces.client import ActivePiecesClient, ap_client_voor
from src.core.activepieces.stappencontrole import (
    NietToegestaneStap,
    controleer_flowdefinitie,
    controleer_graaf,
)
from src.core.activepieces.transformer import FlowTransformer
from src.domains.flows.models import FlowUpdate, ReactFlowGraph
from src.domains.flows.repository import FlowRepository


class FocusBuilderService:
    """
    Service layer for Focus Builder business logic.
    Handles Flow validation, compilation, and integration with ActivePieces.
    """

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.repository = FlowRepository(db, tenant_id)
        self._ap_client: ActivePiecesClient | None = None
        # Note: FlowTransformer uses static methods, no instance needed

    async def ap_client(self) -> ActivePiecesClient:
        """Lazy-initialised AP client van DEZE tenant -- de verbinding pas bij het eerste gebruik."""
        if self._ap_client is None:
            self._ap_client = await ap_client_voor(self.tenant_id, self.db)
        return self._ap_client

    async def create_flow(
        self,
        name: str,
        graph: ReactFlowGraph,
        description: str | None = None,
        created_by: int | None = None,
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        """
        Create a new flow.

        1. Validates graph structure (cycles, single trigger).
        2. Compiles to ActivePieces JSON.
        3. Saves flow to DB first (primary persistence).
        4. Syncs to ActivePieces as a graceful side-effect.
        """
        # Step 1: Compile & Validate using static method
        try:
            ap_flow_json = FlowTransformer.react_flow_to_activepieces(graph.model_dump())
        except Exception as e:
            raise ValueError(f"Invalid Flow Graph: {str(e)}")
        # Voor het opslaan: de AP-sync hieronder slikt elke fout in, dus een weigering
        # daar zou de flow toch lokaal laten staan (wfb-dag1 stap 1).
        controleer_flowdefinitie(ap_flow_json)

        # Step 2: Save to DB first -- this is the source of truth
        flow_record = await self.repository.create(
            {
                "name": name,
                "description": description,
                "react_flow_graph": graph.model_dump(),
                "activepieces_flow_id": None,
                "activepieces_project_id": None,
                "activepieces_flow_json": ap_flow_json,
                "created_by": created_by,
            }
        )

        # Commit before external I/O -- never hold a transaction open during HTTP calls.
        await self.db.commit()
        await self.db.refresh(flow_record)

        # Step 3: Sync to ActivePieces (graceful degradation)
        try:
            project_id = await self._get_tenant_ap_project_id()
            flow_def = {
                "displayName": name,
                "projectId": project_id,
                "trigger": ap_flow_json["trigger"],
            }

            ap_response = await (await self.ap_client()).create_flow(project_id, flow_def)
            ap_flow_id: str | None = cast(str | None, ap_response.get("id"))

            if not ap_flow_id:
                raise ValueError("ActivePieces did not return a Flow ID")

            if "nextAction" in ap_flow_json:
                await (await self.ap_client()).update_flow(ap_flow_id, ap_flow_json)

            await self.repository.update(
                flow_record.id,
                {
                    "activepieces_flow_id": ap_flow_id,
                    "activepieces_project_id": project_id,
                },
            )
            flow_record.activepieces_flow_id = ap_flow_id
            flow_record.activepieces_project_id = project_id

        except Exception as ap_error:
            logger.warning(
                "create_flow_ap_sync_failed: %s: %s",
                type(ap_error).__name__,
                ap_error,
                exc_info=True,
            )
            # Flow is safely persisted in DB; AP sync can be retried later.

        return flow_record

    async def update_flow(
        self, flow_id: int, flow_in: FlowUpdate
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Update an existing flow. Persists all supplied fields; AP sync is best-effort."""
        flow = await self.repository.get(flow_id)
        if not flow:
            raise ValueError("Flow not found or access denied")

        # Gather scalar updates from the request
        updates = flow_in.model_dump(exclude_unset=True)
        graph = updates.pop("react_flow_graph", None)

        # If a graph is supplied, compile it and prepare AP JSON
        if graph is not None:
            if not isinstance(graph, ReactFlowGraph):
                graph = ReactFlowGraph.model_validate(graph)
            try:
                ap_flow_json = FlowTransformer.react_flow_to_activepieces(graph.model_dump())
            except Exception as e:
                raise ValueError(f"Invalid Flow Graph: {str(e)}")
            controleer_flowdefinitie(ap_flow_json)

            updates["react_flow_graph"] = graph.model_dump()
            updates["activepieces_flow_json"] = ap_flow_json
            updates["activepieces_version"] = (flow.activepieces_version or 0) + 1
            updates["updated_at"] = datetime.now(timezone.utc)

            # Persist DB update first
            updated_flow = await self.repository.update(flow_id, updates)
            if not updated_flow:
                raise ValueError("Flow not found or access denied")

            # Best-effort sync to ActivePieces
            if flow.activepieces_flow_id is not None:
                try:
                    ap_flow_json["displayName"] = updated_flow.name
                    await (await self.ap_client()).update_flow(flow.activepieces_flow_id, ap_flow_json)
                except Exception as ap_error:
                    logger.warning(
                        "update_flow_ap_sync_failed: %s: %s",
                        type(ap_error).__name__,
                        ap_error,
                        exc_info=True,
                    )
            else:
                logger.info(
                    "update_flow_no_ap_id: flow_id=%s tenant_id=%s",
                    flow_id,
                    self.tenant_id,
                )

            return updated_flow

        # No graph: simple scalar update. Publiceren van een bestaande flow controleert de
        # opgeslagen graaf: die kan van voor deze controle zijn (wfb-dag1 stap 1).
        if updates.get("is_published"):
            controleer_graaf(flow.react_flow_graph)
        updates["updated_at"] = datetime.now(timezone.utc)
        updated_flow = await self.repository.update(flow_id, updates)
        if not updated_flow:
            raise ValueError("Flow not found or access denied")
        return updated_flow

    async def execute_flow(
        self,
        flow_id: int,
        payload: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Trigger flow execution."""
        flow = await self.repository.get(flow_id)
        if not flow:
            raise ValueError("Flow not found")

        # Check if flow has been synced to ActivePieces
        if flow.activepieces_flow_id is None:
            raise ValueError("Flow has not been synced to ActivePieces yet")
        controleer_graaf(flow.react_flow_graph)

        # Trigger
        try:
            run = await (await self.ap_client()).trigger_flow(flow.activepieces_flow_id, payload or {})
        except NietToegestaneStap:
            raise
        except Exception as e:
            raise ValueError(f"Failed to trigger flow: {str(e)}")

        # Log execution
        current_count = flow.execution_count or 0
        await self.repository.update(
            flow_id,
            {
                "last_executed_at": datetime.now(timezone.utc),
                "execution_count": current_count + 1,
            },
        )

        return {
            "execution_id": run.get("id"),
            "status": run.get("status"),
            "flow_id": flow_id,
        }

    async def get_pieces_catalog(
        self, search: str | None = None, category: str | None = None
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get pieces, syncing if cache is stale."""
        # Simple sync-on-demand for MVP if cache is empty
        # Real impl would check timestamp
        pieces = await self.repository.get_pieces(search, category)

        if not pieces and not search:
            # Empty cache, force sync (gracefully degrade if AP unavailable)
            try:
                await self.sync_pieces_catalog()
                pieces = await self.repository.get_pieces(search, category)
            except ValueError as e:
                logger.warning("pieces_sync_skipped_no_credentials: %s", e)

        return pieces

    async def get_piece_schema(
        self, piece_name: str
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get schema for a specific piece."""
        piece = await self.repository.get_piece(piece_name)
        if not piece:
            # Try to fetch fresh just in case (gracefully degrade if AP unavailable)
            try:
                await self.sync_pieces_catalog()
                piece = await self.repository.get_piece(piece_name)
            except ValueError as e:
                logger.warning("piece_schema_sync_skipped_no_credentials: %s", e)

        if not piece:
            return None

        return {
            "name": piece.piece_name,
            "displayName": piece.display_name,
            "actions": piece.actions,
            "triggers": piece.triggers,
            "authConfig": piece.auth_config,
        }

    async def sync_pieces_catalog(self) -> None:
        """Fetch all pieces from AP and update local DB."""
        ap_pieces = await (await self.ap_client()).list_pieces()

        for p in ap_pieces:
            # Map API model to DB dict
            data = {
                "piece_name": p.name,
                "piece_version": p.version,
                "display_name": p.display_name,
                "description": p.description,
                "logo_url": p.logo_url,
                "actions": p.actions,  # Assuming client returns parsed dicts
                "triggers": p.triggers,
                "auth_config": {},  # Adjust based on actual API response structure
                "last_synced_at": datetime.now(timezone.utc),
            }
            await self.repository.upsert_piece(data)

    async def _get_tenant_ap_project_id(self) -> str:
        """
        Get the ActivePieces Project ID for this tenant.

        Het project komt uit de verbinding van de tenant (`ap_verbinding_voor`); er is geen
        zoekopdracht meer die het eerste project van de server kiest (ADR-040 B4).
        """
        return (await self.ap_client()).project_id
