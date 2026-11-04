"""Tests for AP MCP Registry."""
import pytest
from src.core.tool_broker.ap_mcp_registry import AP_PIECES_MVP, DEPARTMENT_DEFAULT_TOOLS, APMCPRegistry

def test_mvp_pieces_loaded() -> None:
    registry = APMCPRegistry()
    pieces = registry.list_pieces()
    assert len(pieces) == 3
    names = {p.name for p in pieces}
    assert "gmail" in names
    assert "google-calendar" in names
    assert "slack" in names

def test_get_piece() -> None:
    registry = APMCPRegistry()
    piece = registry.get_piece("gmail")
    assert piece is not None
    assert piece.npm_package == "@activepieces/piece-gmail"

def test_get_piece_unknown() -> None:
    registry = APMCPRegistry()
    assert registry.get_piece("unknown") is None

def test_department_default_tools() -> None:
    registry = APMCPRegistry()
    tools = registry.get_default_tools_for_department("sales")
    assert "gmail.send_email" in tools

def test_build_server_params() -> None:
    registry = APMCPRegistry()
    piece = registry.get_piece("gmail")
    assert piece is not None
    params = registry.build_server_params(piece, tenant_id=1, auth_token="tok")
    assert params["command"] == "node"
    assert "--mcp" in params["args"]
    assert params["env"]["AP_PIECE_AUTH"] == "tok"
