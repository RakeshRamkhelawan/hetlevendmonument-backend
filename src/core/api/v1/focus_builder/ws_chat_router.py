"""
FocusBuilder WebSocket chat sub-router (ADR-033 Laag 1).

Routes:
- WS /ws/chat
"""
# orphan:exempt reason: single-responsibility endpoint group, size driven by WS message-type dispatch protocol

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.activepieces.stappencontrole import NietToegestaneStap, controleer_graaf
from src.core.api.dependencies import controleer_resource_recht
from src.core.api.v1.focus_builder.shared import WSUser, validate_ws_token
from src.core.api.v1.focus_builder.dependencies import (  # own-domain -- ADR-033
    FocusBuilderChatAgent,
    FocusBuilderToolAgent,
    KlantStilgezet,
    eis_chat_actief,
    get_db,
)
from src.core.middleware.tenant_context import set_tenant_id
from src.core.shared.config import get_settings as _get_settings


ws_chat_router = APIRouter()

# Berichttypen die een flow wegschrijven of uitvoeren. Elk vraagt `workflows:publish`, net als de
# HTTP-flowroutes (`require_resource_permission`). Bewaakt door
# tests/architecture/test_flow_ingangen_lopen_langs_de_stappencontrole.py.
SCHRIJVENDE_BERICHTTYPEN: frozenset[str] = frozenset({"accept_proposal", "execute"})

# Berichttypen die het taalmodel aanroepen. Voor elk daarvan controleert de socket de noodstop
# (besluit A ronde 2). `execute` loopt via de workflow-engine en is daar al een deur.
MODEL_BERICHTTYPEN: frozenset[str] = frozenset(
    {"message", "refine", "explain", "node_updated", "template_action"}
)


async def mag_flows_publiceren(websocket: WebSocket, db: AsyncSession, user: WSUser) -> bool:
    """De rolcontrole `workflows:publish` voor een websocketbericht.

    Een websocket heeft geen dependency per bericht, dus de controle loopt hier expliciet,
    met dezelfde logica als `require_resource_permission`. Bij weigering gaat er een
    `error`-bericht over de socket en geeft de functie False: de aanroeper schrijft niets weg.
    """
    try:
        await controleer_resource_recht(
            db, int(user.id), int(user.tenant_id), "workflows", "publish"
        )
    except HTTPException as exc:
        await websocket.send_json(
            {"type": "error", "code": "PERMISSION_DENIED", "message": str(exc.detail)}
        )
        return False
    return True


@ws_chat_router.websocket("/ws/chat")
async def focus_builder_ws_chat(
    websocket: WebSocket,
    conversation_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    WebSocket endpoint for Focus Builder AI chat.

    Connection: ws://host/api/v1/focus-builder/ws/chat -- authenticatie via de
    HTTP-only ``access_token``-cookie.

    SEC-AGT-004: de ``?token={jwt}``-variant is verwijderd (2026-07-31). OWASP ASVS V7
    verbiedt sessie-identifiers in query strings; de frontend
    (frontend/src/hooks/useFocusBuilderWS.ts) stuurde al alleen conversation_id mee en
    leunde op de cookie. Afgedwongen door
    tests/architecture/test_websocket_no_query_param_token.py.

    Protocol: see docs/IMPLEMENTATION_PLANS/FOCUS_BUILDER_STREAMING_REDESIGN.md

    Rate: 3/minute (AI endpoint -- LLM-backed)
    """
    # Lazy import to keep FocusBuilder router startup light.
    from src.domains.flows.service import FocusBuilderService

    effective_token = websocket.cookies.get("access_token")
    if not effective_token:
        await websocket.close(code=4001, reason="Missing token")
        logger.warning("ws_chat_rejected_no_token")
        return

    try:
        user = await validate_ws_token(effective_token)
    except Exception as e:
        await websocket.close(code=4003, reason="Invalid token")
        logger.warning("ws_chat_rejected_invalid_token: %s", e, exc_info=True)
        return

    set_tenant_id(user.tenant_id)
    await websocket.accept()
    logger.info(
        "ws_chat_connected",
        user_id=user.id,
        tenant_id=user.tenant_id,
    )

    _settings = _get_settings()
    agent: Any  # TODO(TYPE): replace Any with concrete type
    if _settings.focus_builder_tool_agent:
        agent = FocusBuilderToolAgent(
            user_id=user.id,
            tenant_id=user.tenant_id,
            user_id_str=str(user.id),
            db=db,
            send_json=websocket.send_json,
            restore_conversation_id=conversation_id,
        )
    else:
        agent = FocusBuilderChatAgent(
            user_id=user.id,
            tenant_id=user.tenant_id,
            user_id_str=str(user.id),
            db=db,
            send_json=websocket.send_json,
            restore_conversation_id=conversation_id,
        )

    try:
        await agent.start_session()

        while True:
            raw = await websocket.receive_json()
            msg_type = raw.get("type")

            # NOODSTOP PER KLANT (ADR-036 OP-03, besluit A ronde 2): de chat is een deur. Een
            # stilgezette klant krijgt de vaste melding en GEEN modelaanroep; de socket blijft open.
            if msg_type in MODEL_BERICHTTYPEN:
                try:
                    await eis_chat_actief(user.tenant_id)
                except KlantStilgezet as stop:
                    await websocket.send_json(
                        {"type": "error", "code": "NOODSTOP", "message": stop.bericht}
                    )
                    continue

            if msg_type in SCHRIJVENDE_BERICHTTYPEN and not await mag_flows_publiceren(
                websocket, db, user
            ):
                continue

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "message":
                await agent.handle_message(
                    content=raw.get("content", ""),
                )

            elif msg_type == "accept_proposal":
                proposal_id = raw.get("proposal_id", "")
                nodes = await agent.accept_proposal(proposal_id)
                flow_id = raw.get("flow_id")
                if flow_id and nodes:
                    try:
                        service = FocusBuilderService(db=db, tenant_id=user.tenant_id)
                        flow = await service.repository.get(flow_id)
                        if flow:
                            current_graph = flow.react_flow_graph or {
                                "nodes": [],
                                "edges": [],
                            }
                            existing_nodes = current_graph.get("nodes", [])
                            existing_edges = current_graph.get("edges", [])
                            nieuwe_graaf = {
                                "nodes": existing_nodes + nodes,
                                "edges": existing_edges,
                            }
                            # Geen voorgestelde stap bewaren die iets naar buiten stuurt
                            # (wfb-dag1 stap 1, Gate 2 MEDIUM-4).
                            controleer_graaf(nieuwe_graaf)
                            await service.repository.update(
                                flow_id, {"react_flow_graph": nieuwe_graaf}
                            )
                    except NietToegestaneStap as exc:
                        await websocket.send_json(
                            {"type": "error", "code": "STEP_NOT_ALLOWED", "message": str(exc)}
                        )
                        continue
                    except Exception as exc:
                        logger.error(
                            "ws_chat_accept_save_failed: %s: %s",
                            type(exc).__name__,
                            exc,
                            exc_info=True,
                        )
                await websocket.send_json({"type": "proposal_accepted", "proposal_id": proposal_id})

            elif msg_type == "reject_proposal":
                proposal_id = raw.get("proposal_id", "")
                agent.reject_proposal(proposal_id)
                await websocket.send_json({"type": "proposal_rejected", "proposal_id": proposal_id})

            elif msg_type == "node_updated":
                await agent.handle_node_updated(
                    node_id=raw.get("node_id", ""),
                    old_agent_id=raw.get("old_agent_id", ""),
                    new_agent_id=raw.get("new_agent_id", ""),
                    workflow_id=raw.get("workflow_id"),
                )

            elif msg_type == "template_action":
                await agent.handle_template_action(
                    action=raw.get("action", "ignore"),
                    template_id=raw.get("template_id", ""),
                )

            elif msg_type == "execute":
                flow_id = raw.get("flow_id")
                if flow_id:
                    try:
                        service = FocusBuilderService(db=db, tenant_id=user.tenant_id)
                        await service.execute_flow(flow_id=flow_id, triggered_by=user.id)  # type: ignore  # NOTE: triggered_by param may have been removed
                    except Exception as exc:
                        logger.opt(exception=True).error("focus_builder_ws_chat mislukt: {}", type(exc).__name__)
                        await websocket.send_json({"type": "exec_error", "message": "Er is een fout opgetreden."})

            elif msg_type == "refine":
                if len(str(raw).encode()) > 200_000:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "payload_too_large",
                        }
                    )
                    continue
                content = raw.get("content", "")
                current_nodes = raw.get("current_nodes", [])
                if not isinstance(current_nodes, list):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "current_nodes must be a list",
                        }
                    )
                    continue
                await agent.handle_refine(content=content, current_nodes=current_nodes)

            elif msg_type == "explain":
                node_id = raw.get("node_id", "")
                node_title = raw.get("node_title", "")
                node_type_str = raw.get("node_type", "")
                if not node_id:
                    continue
                await agent.handle_explain(
                    node_id=node_id, node_title=node_title, node_type=node_type_str
                )

    except WebSocketDisconnect:
        logger.info("ws_chat_disconnected", user_id=user.id)
    except Exception as exc:
        logger.error("ws_chat_error: %s: %s", type(exc).__name__, exc, exc_info=True)
        try:
            await websocket.close(code=1011)
        except Exception as close_exc:
            logger.warning("ws_chat_close_failed: %s", close_exc, exc_info=True)
