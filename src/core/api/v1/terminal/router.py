"""
CLI Tool Executor WebSocket endpoint.
Feature 8: Secure sandboxed command execution via WebSocket.

WARNING: This endpoint executes commands in a sandboxed environment.
It should only be enabled in development or with strict security controls.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from src.core.auth.api_deps import get_current_user, require_admin, WebSocketAuthenticator
from src.core.models.rbac_models import User
from src.core.api.v1.terminal.dependencies import (
    TerminalRequest,
    TerminalResponse,
    _require_terminal_enabled,
    is_command_allowed,
    execute_command,
)

_auth = WebSocketAuthenticator()

logger = logging.getLogger(__name__)

router = APIRouter(tags=["cli-executor"])


@router.get("/status", response_model=dict)
async def terminal_status() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get terminal endpoint status."""
    _require_terminal_enabled()
    from src.core.api.v1.terminal.dependencies import _ENVIRONMENT, _TERMINAL_ENABLED

    return {
        "status": "enabled",
        "environment": _ENVIRONMENT,
        "terminal_enabled": _TERMINAL_ENABLED,
    }


@router.post(
    "/execute",
    response_model=TerminalResponse,
    # Beide controles als dependency, dus voor de validatie van de body (plan nazorg, punt d):
    # eerst of de terminal in deze omgeving bestaat, dan de beheerdersrol. Tot 2026-10-08 was er
    # GEEN rolcontrole: elke ingelogde gebruiker mocht in een ontwikkelomgeving commando's draaien.
    dependencies=[Depends(_require_terminal_enabled), Depends(require_admin)],
)
async def execute_command_http(
    cmd_request: TerminalRequest,
    current_user: User = Depends(get_current_user),
) -> TerminalResponse:
    """Execute a terminal command via HTTP endpoint."""

    command = cmd_request.command.strip()
    if not command:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Command cannot be empty")

    if not is_command_allowed(command):
        from fastapi import HTTPException
        from src.core.api.v1.terminal.dependencies import ALLOWED_COMMANDS

        raise HTTPException(
            status_code=403,
            detail=f"Command not allowed. Allowed commands: {', '.join(sorted(ALLOWED_COMMANDS))}",
        )

    logger.info("Executing command via HTTP: %s", command)
    stdout, stderr, return_code = await execute_command(command)

    return TerminalResponse(
        stdout=stdout,
        stderr=stderr,
        return_code=return_code,
    )


@router.websocket("/ws/terminal")
async def terminal_ws(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for terminal emulation.
    """
    user = await _auth.authenticate(websocket)
    if not user:
        return
    logger.info("Terminal WebSocket connected")

    import os

    cli_enabled = os.getenv("ENABLE_CLI_EXECUTOR", "false").lower() == "true"

    if not cli_enabled:
        await websocket.send_json(
            {
                "type": "error",
                "data": "CLI executor is disabled. Set ENABLE_CLI_EXECUTOR=true to enable.",
            }
        )
        await websocket.close()
        return

    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")

            if msg_type == "command":
                command = message.get("data", "").strip()

                if not command:
                    await websocket.send_json({"type": "stderr", "data": "Empty command\n"})
                    continue

                if not is_command_allowed(command):
                    from src.core.api.v1.terminal.dependencies import ALLOWED_COMMANDS

                    await websocket.send_json(
                        {
                            "type": "stderr",
                            "data": f"Command not allowed. Allowed commands: {', '.join(sorted(ALLOWED_COMMANDS))}\n",
                        }
                    )
                    await websocket.send_json({"type": "exit", "code": 1})
                    continue

                logger.info("Executing command: %s", command)

                stdout, stderr, code = await execute_command(command)

                if stdout:
                    await websocket.send_json({"type": "stdout", "data": stdout})

                if stderr:
                    await websocket.send_json({"type": "stderr", "data": stderr})

                await websocket.send_json({"type": "exit", "code": code})

            elif msg_type == "resize":
                cols = message.get("cols", 80)
                rows = message.get("rows", 24)
                logger.debug("Terminal resize: %sx%s", cols, rows)

    except WebSocketDisconnect:
        logger.info("Terminal WebSocket disconnected")
    except OSError:
        logger.error("Terminal WebSocket OS error", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "data": "Command execution failed"})
        except Exception:
            logger.debug("Failed to send websocket error payload", exc_info=True)
    except ValueError:
        logger.error("Terminal WebSocket value error", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "data": "Invalid command"})
        except Exception:
            logger.debug("Failed to send websocket error payload", exc_info=True)
