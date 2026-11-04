from typing import Any, Optional, cast
from collections.abc import Sequence

import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.activepieces.client import ActivePiecesClient, ap_client_voor
from src.core.activepieces.transformer import FlowTransformer
from src.core.focus_builder.models import FocusBuilderFlow
from src.core.focus_builder.repositories import FlowRepository, PiecesRepository
from src.core.focus_builder.schemas import FlowCreate, FlowUpdate


class FocusBuilderService:
    """
    Business logic layer for FocusBuilder workflow management.

    Orchestrates between:
    - FlowRepository (database operations)
    - ActivePiecesClient (workflow engine)
    - FlowTransformer (graph conversion)
    """

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self.session = db
        self._tenant_id = tenant_id
        self.flow_repo = FlowRepository(db, tenant_id)
        self.piece_repo = PiecesRepository(db)
        self._ap_client: ActivePiecesClient | None = None

    async def ap_client(self) -> ActivePiecesClient:
        """De client van deze tenant; pas bij het eerste gebruik, zodat een tenant zonder
        verbinding wel de lokale flows kan lezen. Ontbreekt de verbinding, dan volgt een
        `ApVerbindingOntbreektError` -- nooit een algemene client."""
        if self._ap_client is None:
            self._ap_client = await ap_client_voor(self._tenant_id, self.session)
        return self._ap_client

    async def create_flow(
        self, flow_data: FlowCreate, user_id: int | None = None
    ) -> FocusBuilderFlow:
        """
        Create a new workflow flow.

        1. Saves to database first (ensures local persistence)
        2. Compiles to ActivePieces format
        3. Syncs to ActivePieces engine (graceful degradation if AP unavailable)
        """
        logger.info(
            "flow_create_started",
            flow_name=flow_data.name,
            tenant_id=self._tenant_id,
            user_id=user_id,
        )

        # 0. Geen verbinding voor deze tenant = een duidelijke fout VOOR de eerste schrijfactie.
        # Anders staat er een flow in de database die nooit naar ActivePieces kan en meldt de
        # "graceful degradation" hieronder alleen een logregel.
        ap_client = await self.ap_client()

        # 1. Save to DB first
        db_flow = await self.flow_repo.create(flow_data.dict())
        logger.info("flow_saved_to_db", flow_id=db_flow.id, flow_name=flow_data.name)

        # 2. Compile to AP JSON
        ap_flow_json = FlowTransformer.react_flow_to_activepieces(
            {"name": flow_data.name, **flow_data.react_flow_graph}
        )

        # 3. Create in ActivePieces (graceful degradation)
        try:
            ap_response = await ap_client.execute_workflow(
                workflow_definition=flow_data.react_flow_graph,
            )

            if ap_response.get("success"):
                await self.flow_repo.update(
                    db_flow.id,
                    {
                        "activepieces_flow_id": ap_response.get("flow_id"),
                    },
                )
                logger.info(
                    "flow_synced_to_activepieces",
                    flow_id=db_flow.id,
                    ap_flow_id=ap_response.get("flow_id"),
                )
        except httpx.HTTPStatusError as e:
            logger.warning(
                "activepieces_sync_failed_http",
                flow_id=db_flow.id,
                status_code=e.response.status_code,
                detail=str(e),
            )
            # Flow is saved locally, AP sync can be retried later
        except httpx.RequestError as e:
            logger.error("activepieces_unreachable", flow_id=db_flow.id, error=str(e))
            # Flow is saved locally, AP is temporarily unavailable
        except Exception as e:
            logger.error(
                "activepieces_sync_unexpected_error",
                flow_id=db_flow.id,
                error=str(e),
                error_type=type(e).__name__,
            )
            # Don't fail the request, flow is saved locally

        return db_flow

    async def update_flow(
        self, flow_id: int, flow_data: FlowUpdate, user_id: int | None = None
    ) -> FocusBuilderFlow | None:
        """Update an existing workflow flow."""
        logger.info("flow_update_started", flow_id=flow_id, user_id=user_id)

        # 1. Update DB
        db_flow = await self.flow_repo.update(flow_id, flow_data.dict(exclude_unset=True))
        if not db_flow:
            logger.warning("flow_update_not_found", flow_id=flow_id)
            return None

        logger.info("flow_updated_in_db", flow_id=flow_id)

        # 2. Sync to AP if graph changed
        if flow_data.react_flow_graph and db_flow.activepieces_flow_id:
            try:
                ap_flow_json = await (await self.ap_client()).build_flow_definition(
                    {"name": db_flow.name, **db_flow.react_flow_graph}
                )
                await (await self.ap_client()).update_flow(db_flow.activepieces_flow_id, ap_flow_json)
                logger.info(
                    "flow_synced_to_activepieces",
                    flow_id=flow_id,
                    ap_flow_id=db_flow.activepieces_flow_id,
                )
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "activepieces_update_failed_http",
                    flow_id=flow_id,
                    status_code=e.response.status_code,
                    detail=str(e),
                )
            except httpx.RequestError as e:
                logger.error("activepieces_unreachable", flow_id=flow_id, error=str(e))
            except Exception as e:
                logger.error(
                    "activepieces_update_unexpected_error",
                    flow_id=flow_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )

        return db_flow

    async def get_flow(self, flow_id: int) -> FocusBuilderFlow | None:
        """Get a flow by ID."""
        flow = await self.flow_repo.get(flow_id)
        if flow:
            logger.debug("flow_retrieved", flow_id=flow_id)
        else:
            logger.debug("flow_not_found", flow_id=flow_id)
        return flow

    async def list_flows(self) -> Sequence[FocusBuilderFlow]:
        """List all flows for the service's tenant."""
        flows = await self.flow_repo.list()
        logger.debug("flows_listed", count=len(flows))
        return flows

    async def delete_flow(self, flow_id: int, user_id: int | None = None) -> bool:
        """Delete a flow by ID."""
        logger.info("flow_delete_started", flow_id=flow_id, user_id=user_id)

        flow = await self.flow_repo.get(flow_id)
        if flow and flow.activepieces_flow_id:
            try:
                await (await self.ap_client()).delete_flow(flow.activepieces_flow_id)
                logger.info(
                    "flow_deleted_from_activepieces",
                    flow_id=flow_id,
                    ap_flow_id=flow.activepieces_flow_id,
                )
            except Exception as e:
                logger.warning("activepieces_delete_failed", flow_id=flow_id, error=str(e))
                # Continue with DB deletion even if AP fails

        result = await self.flow_repo.delete(flow_id)
        if result:
            logger.info("flow_deleted", flow_id=flow_id)
        else:
            logger.warning("flow_delete_not_found", flow_id=flow_id)
        return result

    async def sync_pieces_catalog(self) -> int:
        """
        Fetch all pieces from ActivePieces and update local cache.
        """
        logger.info("pieces_catalog_sync_started")

        try:
            pieces = await (await self.ap_client()).list_pieces()
        except Exception as e:
            logger.error("pieces_catalog_fetch_failed", error=str(e))
            raise

        count = 0
        for p in pieces:
            data = {
                "piece_name": p.name,
                "display_name": p.display_name,
                "logo_url": str(p.logo_url) if p.logo_url else None,
                "actions": p.actions,
                "triggers": p.triggers,
            }
            await self.piece_repo.upsert_piece(data)
            count += 1

        await self.session.commit()
        logger.info("pieces_catalog_sync_completed", count=count)
        return count

    async def get_latest_run_status(self, flow_id: int) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get the latest run status for a flow."""
        flow = await self.get_flow(flow_id)
        if not flow or not flow.activepieces_flow_id:
            logger.debug("run_status_no_flow", flow_id=flow_id)
            return {"status": "UNKNOWN"}

        try:
            runs = await (await self.ap_client()).list_runs(flow.activepieces_flow_id, limit=1)
            if runs:
                logger.debug("run_status_retrieved", flow_id=flow_id, run_id=runs[0].get("id"))
                return runs[0]
            return {"status": "UNKNOWN"}
        except httpx.HTTPStatusError as e:
            logger.warning(
                "run_status_fetch_failed_http",
                flow_id=flow_id,
                status_code=e.response.status_code,
            )
            return {"status": "UNKNOWN", "error": "fetch_failed"}
        except httpx.RequestError as e:
            logger.error("activepieces_unreachable_for_runs", flow_id=flow_id, error=str(e))
            return {"status": "UNKNOWN", "error": "service_unavailable"}
        except Exception as e:
            logger.error(
                "run_status_unexpected_error",
                flow_id=flow_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return {"status": "UNKNOWN", "error": "unexpected_error"}

    async def get_run_logs(self, run_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get detailed logs for a specific run."""
        logger.debug("run_logs_requested", run_id=run_id)
        try:
            return await (await self.ap_client()).get_run_logs(run_id)
        except Exception as e:
            logger.error("run_logs_fetch_failed", run_id=run_id, error=str(e))
            return {"error": str(e)}

    async def generate_flow_from_prompt(self, prompt: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate a flow from a natural language prompt.

        Currently uses a simple template-based approach.
        In production, this would call an LLM service.
        """
        logger.info("flow_generation_started", prompt_length=len(prompt))

        if "loop" in prompt.lower():
            graph = {
                "nodes": [
                    {
                        "id": "1",
                        "type": "trigger",
                        "data": {"label": "On Loop Trigger"},
                        "position": {"x": 100, "y": 50},
                    },
                    {
                        "id": "2",
                        "type": "loop",
                        "data": {"label": "Loop Items"},
                        "position": {"x": 100, "y": 150},
                    },
                ],
                "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
            }
        else:
            graph = {
                "nodes": [
                    {
                        "id": "1",
                        "type": "trigger",
                        "data": {"label": "Generated Trigger"},
                        "position": {"x": 100, "y": 50},
                    },
                    {
                        "id": "2",
                        "type": "action",
                        "data": {"label": "Generated Action"},
                        "position": {"x": 100, "y": 150},
                    },
                ],
                "edges": [{"id": "e1-2", "source": "1", "target": "2"}],
            }

        logger.info("flow_generation_completed", node_count=len(cast(Any, graph["nodes"])))  # TODO(TYPE): replace Any with concrete type
        return {"graph": graph}
