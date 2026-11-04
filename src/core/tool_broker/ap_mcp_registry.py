"""AP MCP Registry -- registers ActivePieces npm pieces as MCP servers.

Plan B: if Node.js is not available, mock responses are used for smoke tests.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

# Het risico van een actie staat NIET hier maar in `src/core/config/tool_risk_levels.yml`, per
# `piece.actie` (bijv. `gmail.send_email`), en wordt gelezen door `ToolRiskClassifier`. Hier stond
# een eigen enum `ToolRisk` met gmail/slack op MEDIUM; alleen HIGH opent de mens-in-de-lus-poort,
# dus een tweede lijst met een ander antwoord liet een mail zonder tussenkomst van een mens weg
# (ADR-040 B12).
@dataclass(frozen=True)
class APPiece:
    name: str
    npm_package: str

AP_PIECES_MVP: list[APPiece] = [
    APPiece(name="gmail", npm_package="@activepieces/piece-gmail"),
    APPiece(name="google-calendar", npm_package="@activepieces/piece-google-calendar"),
    APPiece(name="slack", npm_package="@activepieces/piece-slack"),
]

# Mapping from department to default tools
DEPARTMENT_DEFAULT_TOOLS: dict[str, list[str]] = {
    "sales": ["gmail.send_email", "slack.send_message"],
    "marketing": ["slack.send_message", "google-calendar.create_event"],
    "finance": ["gmail.send_email"],
    "hr": ["gmail.send_email", "google-calendar.create_event"],
    "support": ["slack.send_message"],
    "operations": ["slack.send_message", "gmail.send_email"],
}

class APMCPRegistry:
    """Registry for ActivePieces MCP pieces."""

    def __init__(self) -> None:
        self._pieces: dict[str, APPiece] = {p.name: p for p in AP_PIECES_MVP}

    def list_pieces(self) -> list[APPiece]:
        return list(self._pieces.values())

    def get_piece(self, name: str) -> APPiece | None:
        return self._pieces.get(name)

    def get_default_tools_for_department(self, department: str) -> list[str]:
        return DEPARTMENT_DEFAULT_TOOLS.get(department, [])

    def build_server_params(self, piece: APPiece, tenant_id: int, auth_token: str | None = None) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Build StdioServerParameters-compatible dict for MCP client."""
        env = {"AP_PIECE_AUTH": auth_token or ""}
        return {
            "command": "node",
            "args": [f"node_modules/{piece.npm_package}/dist/index.js", "--mcp"],
            "env": env,
        }

# Global registry instance
ap_mcp_registry = APMCPRegistry()
