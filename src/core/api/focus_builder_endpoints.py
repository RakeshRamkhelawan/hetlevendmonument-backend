# orphan:exempt reason: nog niet gemigreerd naar v1/; TODO(SP-VOLGENDE): migreer naar v1/<domein>/
"""
FocusBuilder Legacy Compatibility Layer.

This module re-exports from the V1 router for backwards compatibility.
All new code should import from src.core.api.v1.focus_builder.router directly.

Deprecated: Use src.core.api.v1.focus_builder.router instead.
"""


# Re-export everything from V1 router for backwards compatibility
from src.core.api.v1.focus_builder.router import (  # noqa: F401
    create_flow,
    delete_flow,
    execute_flow,
    generate_flow_ai,
    get_flow,
    get_focus_builder_service,
    get_latest_run,
    get_run_logs,
    list_flows,
    list_pieces,
    router,
    sync_pieces,
    update_flow,
)

__all__ = [
    "create_flow",
    "delete_flow",
    "execute_flow",
    "generate_flow_ai",
    "get_flow",
    "get_focus_builder_service",
    "get_latest_run",
    "get_run_logs",
    "list_flows",
    "list_pieces",
    "router",
    "sync_pieces",
    "update_flow",
]
