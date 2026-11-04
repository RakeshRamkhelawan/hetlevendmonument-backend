# orphan:exempt reason: legacy flat file, replaced by src/core/api/v1/tool_broker/ (SP-API-005 Dag 4)
"""
Tool Broker Endpoints - FASE 4 Production RBAC Protection
Re-export shim: routes live in src/core/api/v1/tool_broker/

This file is retained for backward compatibility with any direct imports.
"""

from typing import Any

from src.core.api.v1.tool_broker.router import router  # noqa: F401

# Module-level data structures for legacy test compatibility.
# These were in the old monolithic endpoint file and are referenced
# by test_tool_broker_api.py for state reset in fixtures.
available_tools: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
tool_execution_history: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

# Compatibility re-export for legacy test patches
try:
    from src.core.tool_broker.service import ToolBrokerService  # noqa: F401
except Exception:
    ToolBrokerService = None  # type: ignore[misc,assignment]
